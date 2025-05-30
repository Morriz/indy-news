import asyncio
import os
from datetime import datetime
from http.cookies import SimpleCookie
from logging import debug, error, info
from typing import Dict, List, Optional

import dotenv
from fastapi import HTTPException
from pydantic import BaseModel
from twikit import Client
from twikit import Tweet as TwikitTweet
from twikit import User as TwikitUser

from api.store import get_data
from lib.cache import async_threadsafe_ttl_cache
from lib.utils import get_since_date

dotenv.load_dotenv()

# client = GuestClient()
client = Client(
    "en-US",
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
)

cookies_file: str = os.path.join(os.getenv("CACHE") or "", "cookies.json")


class User(BaseModel, TwikitUser):
    # The unique identifier of the user.
    id: int
    # The screen name of the user.
    screen_name: str


class Tweet(BaseModel, TwikitTweet):
    # The unique identifier of the tweet.
    id: str
    # The full text of the tweet.
    text: str
    # The language of the tweet.
    lang: str
    # Hashtags included in the tweet text.
    hashtags: List[str]
    # User that created the tweet.
    user: User


async def _get_client() -> Client:
    # if exists, load cookies from file
    if client._user_id is not None:
        return client
    if os.getenv("X_COOKIES"):
        info("Using cookies from environment variable X_COOKIES")
        cookies_raw = os.getenv("X_COOKIES")
        cookie = SimpleCookie()
        cookie.load(cookies_raw)
        cookies = {k: v.value for k, v in cookie.items()}
        client.set_cookies(cookies)
        return client
    if os.path.exists(cookies_file):
        info(f"Loading cookies from file: {cookies_file}")
        client.load_cookies(cookies_file)
        return client
    # otherwise, login
    info("No cookies found, logging in with credentials")
    await client.login(
        auth_info_1=os.getenv("X_USER"),
        auth_info_2=os.getenv("X_EMAIL"),
        password=os.getenv("X_PASSWORD"),
    )
    # and save cookies to file
    client.save_cookies(cookies_file)
    return client


# cache results for one hour
@async_threadsafe_ttl_cache(ttl=3600)
async def x_search(
    users: Optional[str],
    query: Optional[str] = None,
    period_days: int = 3,
    end_date: Optional[str] = None,
    max_tweets_per_user: int = 20,
) -> List[Tweet]:
    """Search for tweets from specific users or matching a query"""
    # Validate parameters
    if users == "":  # Empty string should be treated as None
        users = None
    if not users and not query:
        raise ValueError("Either users or query must be provided")
    if period_days <= 1:
        raise ValueError("period_days must be 1 or more")
    if end_date:
        try:
            date = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            if "does not match format" in str(e):
                raise ValueError("end_date must be in YYYY-MM-DD format")
            raise e

    debug(
        f"Searching for tweets with users: {users}, query: {query}, period_days: {period_days}, end_date: {end_date}, max_tweets_per_user: {max_tweets_per_user}"
    )
    # Process users if provided
    users_arr = []
    if users:
        users_arr = [f"from:{user}" for user in _filter_users(users.lower().split(","))]

    # Build search query
    query_str = f" {query}" if query else ""
    [year, month, day] = get_since_date(period_days, end_date)
    since = f"since:{year}-{month}-{day} "
    until = f"until:{end_date}" if end_date else ""
    users_str = " (" + " OR ".join(users_arr) + ")" if len(users_arr) > 0 else ""
    search = f"{since}{until}{users_str}{query_str}".strip()

    # Set tweet count based on number of users
    count = len(users_arr) * max_tweets_per_user if users_arr else max_tweets_per_user

    tweets: List[Tweet] = []
    try:
        client = await _get_client()
        _tweets = await client.search_tweet(
            query=search,
            product="Latest",
            count=count,
        )
        tweets.extend(_tweets)
        while (len(_tweets) == 20) and len(tweets) < count:
            _tweets = await _tweets.next()
            tweets.extend(_tweets)
            await asyncio.sleep(1)
        print("Number of tweets found: " + str(len(tweets)))
        return _max_per_user(tweets, max_tweets_per_user)
    except Exception as e:
        if isinstance(e, HTTPException):
            # raise e
            error(e)
        else:
            err = HTTPException(
                status_code=500, detail=f"Failed to fetch tweets: {str(e)}"
            )
            # raise err
            error(err)
        return []


def _max_per_user(tweets: List[Tweet], max_tweets_per_user: int = 10) -> List[Tweet]:
    ret: Dict[int, List[Tweet]] = {}
    for tweet in tweets:
        if not tweet.user.id in ret:
            ret[tweet.user.id] = []
        if len(ret[tweet.user.id]) >= max_tweets_per_user:
            break
        ret[tweet.user.id].append(tweet)
    # flatten the dict
    return [tweet for tweets in ret.values() for tweet in tweets]


def _filter_users(users: List[str]) -> List[str]:
    """Only allow users in our data store"""
    data = get_data()
    fixed_users = []
    for user in users:
        # look up as partial match in our db
        found = next(
            (item for item in data if user.lower() in str(item.get("X", "")).lower()),
            None,
        )
        if found and found["X"] and found["X"].lower() != "n/a":
            fixed_users.append(found["X"])
    return fixed_users
