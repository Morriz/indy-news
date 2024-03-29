import asyncio

import streamlit as st

from api.main import search_youtube

st.sidebar.title("Indy News Search")
st.title("Youtube overview by topic")
st.markdown(
    """
## Get an overview of youtube videos that indy media are publishing on a topic.
First uses "Media" endpoint to find sources and then queries youtube for videos from those sources.
(Results are cached one hour.)
"""
)
query = st.text_input("Search for topics/keywords...", value="israel", max_chars=255)

max_channels = st.slider("Select max number of channels", 1, 25, (8))
max_videos_per_channel = st.slider(
    "Select max number of videos per channel", 1, 25, (3)
)
period_days = st.text_input("Period (days since now)", 1)

if query == "":
    st.stop()


async def get_youtube_results() -> None:
    results = await search_youtube(
        query, period_days, max_channels, max_videos_per_channel
    )

    for item in results:
        #     st.markdown(
        #         f"[{item['title']}](https://www.youtube.com{item['url_suffix']})",
        #     )
        st.video(f"https://www.youtube.com{item['url_suffix']}")


asyncio.run(get_youtube_results())
