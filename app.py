from openai import OpenAI
import streamlit as st
import openai
import time
import json
from bs4 import BeautifulSoup
import requests
import wikipedia
from duckduckgo_search import DDGS
import os

st.sidebar.title("API Key")
st.session_state.api_key = st.sidebar.text_input("Enter your OpenAI API Key", type="password")
st.sidebar.markdown("GitHub Repo:: ")

if not st.session_state.api_key:
    st.warning("Please enter your OpenAI API Key in the sidebar.")
    st.stop()

openai.api_key = st.session_state.api_key
client = OpenAI(api_key=st.session_state.api_key)

assistant_id_key = "assistant_id"
thread_id_key = "thread_id"

functions = [
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": "Search for a topic on Wikipedia and return a summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The topic to search"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_duckduckgo",
            "description": "Search DuckDuckGo and return the top result URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The topic to search"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_website",
            "description": "Extract text content from a given webpage URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL of the page to extract"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_file",
            "description": "Save the provided text to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The research text to save"}
                },
                "required": ["text"]
            }
        }
    }
]

def search_wikipedia(query: str) -> str:
    try:
        return wikipedia.summary(query, sentences=5)
    except Exception as e:
        return f"Wikipedia error: {str(e)}"

def search_duckduckgo(query: str) -> str:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=1))
        return results[0]["href"] if results else "No results found."

def scrape_website(url: str) -> str:
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator="\n")[:1000]
    except Exception as e:
        return f"Scraping error: {str(e)}"

def save_to_file(text: str) -> str:
    filename = "research.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)
    return filename

if assistant_id_key not in st.session_state:
    assistant = client.beta.assistants.create(
        name="Research Assistant",
        instructions="You are a research assistant who uses tools to gather information, extract website content, and save it to a file.",
        model="gpt-4o-mini-2024-07-18",
        tools=functions
    )
    st.session_state[assistant_id_key] = assistant.id

if thread_id_key not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state[thread_id_key] = thread.id

st.title("Research Assistant with Tools")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "preset_triggered" not in st.session_state:
    st.session_state.preset_triggered = False

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

preset_question = "Research about the XZ backdoor"
if st.button("Research about the XZ Backdoor"):
    st.session_state.preset_triggered = True
    st.session_state.preset_text = preset_question

if st.session_state.get("preset_triggered"):
    default_input = st.session_state.get("preset_text", "")
    st.session_state.preset_triggered = False
else:
    default_input = ""

user_input = st.chat_input("Ask me to research something...", key="chatbox") or default_input

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    if "active_run" in st.session_state:
        run_check = client.beta.threads.runs.retrieve(
            thread_id=st.session_state[thread_id_key],
            run_id=st.session_state["active_run"]
        )
        if run_check.status not in ["completed", "failed", "cancelled"]:
            st.warning(f"Previous run still active: {run_check.status}")
            st.stop()

    client.beta.threads.messages.create(
        thread_id=st.session_state[thread_id_key],
        role="user",
        content=user_input
    )

    run = client.beta.threads.runs.create(
        thread_id=st.session_state[thread_id_key],
        assistant_id=st.session_state[assistant_id_key]
    )
    st.session_state["active_run"] = run.id

    with st.chat_message("assistant"):
        status_area = st.empty()
        full_response = ""

        while True:
            run = client.beta.threads.runs.retrieve(
                thread_id=st.session_state[thread_id_key],
                run_id=run.id
            )

            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []

                for call in tool_calls:
                    function_name = call.function.name
                    arguments = json.loads(call.function.arguments)

                    allowed_args = {}
                    if function_name == "search_wikipedia":
                        allowed_args = {"query": arguments.get("query")}
                        result = search_wikipedia(**allowed_args)
                    elif function_name == "search_duckduckgo":
                        allowed_args = {"query": arguments.get("query")}
                        result = search_duckduckgo(**allowed_args)
                    elif function_name == "scrape_website":
                        allowed_args = {"url": arguments.get("url")}
                        result = scrape_website(**allowed_args)
                    elif function_name == "save_to_file":
                        allowed_args = {"text": arguments.get("text")}
                        filename = save_to_file(**allowed_args)
                        st.markdown("파일이 준비되었습니다. 아래 버튼을 눌러 다운로드하세요.")
                        with open(filename, "rb") as f:
                            st.download_button(
                                label="Download saved research",
                                data=f,
                                file_name=filename,
                                mime="text/plain"
                            )
                        result = "File saved successfully."
                    else:
                        result = f"No handler for {function_name}"

                    tool_outputs.append({
                        "tool_call_id": call.id,
                        "output": result
                    })

                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=st.session_state[thread_id_key],
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
                run = client.beta.threads.runs.retrieve(
                    thread_id=st.session_state[thread_id_key],
                    run_id=run.id
                )

            elif run.status == "completed":
                break

            status_area.markdown(f"Status: `{run.status}`")
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=st.session_state[thread_id_key])
        assistant_messages = [m for m in messages.data if m.role == "assistant"]
        latest = assistant_messages[0].content[0].text.value
        st.markdown(latest)
        st.session_state.messages.append({"role": "assistant", "content": latest})