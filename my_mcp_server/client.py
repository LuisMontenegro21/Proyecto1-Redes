# 19/09/2025
# Reference: https://modelcontextprotocol.io/quickstart/client 
import asyncio, os, traceback, platform
from contextlib import AsyncExitStack
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from mcp.client.streamable_http import streamablehttp_client
from dotenv import load_dotenv
from pathlib import Path
from types import SimpleNamespace


load_dotenv() # load environmental variables    

# set agent config
AGENT_SYSTEM = (
"You can use tools via a single function mcp_call_tool.\n"
    "When a tool is needed, call mcp_call_tool with:\n"
    '{"tool_name":"<exact name>","arguments":{...}}\n'
    "If a user request is actionable by a tool, you MUST call mcp_call_tool rather than answering in plain text.\n"
    "If there are schema parameters missing for a tool call, reply what are the parameters and which ones are missing\n"
    "You must use exact tool names from the manifest when calling mcp_call_tool."
)

def save_history_jsonl(history: list[dict], path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for m in history:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

def load_history_jsonl(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    msgs = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msgs.append(json.loads(line))
    return msgs

def _append_history(history: list[dict], new_msgs: list[dict], keep_last:int=50) -> list[dict]:
    """Append and keep only the most recent N messages."""
    history.extend(new_msgs)
    if keep_last and len(history) > keep_last:
        # keep the system message if you have one at index 0
        sys = history[:1] if history and history[0].get("role") == "system" else []
        tail = history[-keep_last:]
        history[:] = (sys + tail) if sys else tail
    return history


def get_documents_root() -> str:
    """
    Return the path to the user's Documents directory in a cross-platform way.
    Works on Windows, macOS, and Linux.
    """
    home = os.path.expanduser("~")

    system = platform.system()
    if system == "Windows":
        docs = os.path.join(home, "Documents")
    elif system == "Darwin":
        docs = os.path.join(home, "Documents")
    else:
        docs = os.path.join(home, "Documents")
    if os.path.isdir(docs):
        return docs
    else:
        return home
    
def _serialize_tool_calls(tool_calls):
    out = []
    for tc in (tool_calls or []):
        # tc has .id, .type, and .function with .name and .arguments (JSON string)
        out.append({
            "id": tc.id,
            "type": tc.type,  # usually "function"
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,  # already a JSON string per API
            }
        })
    return out


def _pp_content(items) -> str:
    chunks: list[str] = []
    for c in items:
        t = getattr(c, "type", None)
        if t == "text":
            chunks.append(c.text)
        elif t == "json":
            try:
                chunks.append(json.dumps(c.data, indent=2))
            except Exception:
                chunks.append(str(c.data))
        elif t == "resource":
            rid = getattr(c, "id", None)
            uri = getattr(c, "uri", None)
            chunks.append(f"[resource] {rid or uri}")
        else:
            chunks.append(repr(c))
    return "\n".join(chunks) if chunks else "(no content)"



def _compact_manifest_items(tools_resp, include_schema: bool = True, max_chars: int = 12000) -> str:
    """Build a compact JSON manifest for the prompt from list_tools() response."""
    items = []
    for t in tools_resp.tools:
        obj = {
            "name": t.name,
            "description": getattr(t, "description", "") or ""
        }
        if include_schema:
            obj["input_schema"] = getattr(t, "inputSchema", getattr(t, "input_schema", None))
        items.append(obj)
    blob = json.dumps(items, indent=2)
    return blob[:max_chars]

async def small_chat(
    session: ClientSession,
    openai_client: OpenAI,
    user_prompt: str,
    model: str = "gpt-4o-mini",
    max_steps: int = 4,
    history: list[dict] | None = None,
    keep_last: int = 50
) -> tuple[str, list[dict]]:
    tools_resp = await session.list_tools()
    tools_manifest = _compact_manifest_items(tools_resp)

    system_msg = {"role" : "system", "content": AGENT_SYSTEM + "\nAvailable Tools:\n" + tools_manifest}
    history = list(history or [])
    if not history or history[0].get("role") != "system":
        history.insert(0, system_msg)

    tools_spec = [{
        "type": "function",
        "function": {
            "name": "mcp_call_tool",
            "description": "Invoke an MCP tool by name with JSON arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["tool_name", "arguments"],
                "additionalProperties": False
            }
        }
    }]

    turn_msgs = [
        # {"role": "system", "content": AGENT_SYSTEM + "\nAvailable tools:\n" + tools_manifest},
        {"role": "user", "content": user_prompt},
    ]
    messages = history + turn_msgs

    last_tool_text: str | None = None

    for _ in range(max_steps):
        resp = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_spec,
            tool_choice="auto",
            temperature=0,
            max_tokens=700,
        )
        msg = resp.choices[0].message

        # 1) If the model is done (no tool_calls) -> return content or fallbacks
        if not getattr(msg, "tool_calls", None):
            content = (msg.content or "").strip()

            turn_msgs.append({"role": "assistant", "content": content})

            updated = _append_history(history, turn_msgs, keep_last=keep_last)
            # Final fallback
            return (content or (last_tool_text or "(no content)")), updated

        shell = {
            "role": "assistant",
            "tool_calls": _serialize_tool_calls(msg.tool_calls),
            "content": msg.content or ""
        }
        turn_msgs.append(shell)
        messages.append(shell)

        # 3) Execute each tool call
        for call in msg.tool_calls:
            if call.function.name != "mcp_call_tool":
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": "Please use mcp_call_tool to invoke MCP tools."
                })
                continue

            try:
                args = json.loads(call.function.arguments or "{}")
                tool_name = args["tool_name"]
                arguments = args.get("arguments", {})
            except Exception as e:
                reply = {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": f"(error) Invalid JSON in tool call: {e}"
                }
                turn_msgs.append(reply)
                messages.append(reply)
                continue

            # Call the MCP tool
            try:
                mcp_result = await session.call_tool(tool_name, arguments)
                tool_text = _pp_content(mcp_result) or "(empty result)"
            except Exception as e:
                tool_text = f"(error) {e}"

            last_tool_text = tool_text
            tool_reply = {
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_text
            }
            turn_msgs.append(tool_reply)
            messages.append(tool_reply)

        continue
    updated = _append_history(history, turn_msgs, keep_last=keep_last)
    return (last_tool_text or "Ran out of steps without an answer"), updated


class Client:
    __slots__ = ('session', 'exit_stack', 'open_ai', '_sessions', '_tool_index')
    def __init__(self) -> None:
        #self.session: ClientSession | None = None
        self.session = None
        self.exit_stack = AsyncExitStack()
        self.open_ai = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

        self._sessions : dict[str, ClientSession] = {}
        self._tool_index : dict[str, tuple[str,str]] = {}

    async def _index(self, prefix: str, sess: ClientSession):
        if prefix in self._sessions:
            raise ValueError(f"prefix '{prefix}' already registered")
        self._sessions[prefix] = sess
        tools = (await sess.list_tools()).tools or []
        for t in tools:
            self._tool_index[f"{prefix}.{t.name}"] = (prefix, t.name)
        self.session = self
        
    async def register_http(self, prefix: str, url: str, headers:dict|None={}):
        read, write, _ = await self.exit_stack.enter_async_context(streamablehttp_client(url=url, headers=headers))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        await self._index(prefix, session)
    
    async def register_stdio(self, prefix: str, params: StdioServerParameters):
        read, write = await self.exit_stack.enter_async_context(stdio_client(params))
        sess = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await sess.initialize()
        await self._index(prefix, sess)

    # redirect tool listing correctly depending of the server
    async def list_tools(self):
        
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name=name,
                    description=f"From '{name.split('.', 1)[0]}' server"
                )
                for name in sorted(self._tool_index.keys())
            ]
        )
    # redirect tool calls depending of the server
    async def call_tool(self, tool_name: str, arguments: dict):
        prefix, plain = self._tool_index[tool_name]
        return await self._sessions[prefix].call_tool(plain, arguments)


    async def connect_to_local_server(self, root_path:str=None, personal_server: bool= True):
        if root_path is None:
            root_path = get_documents_root()
        
        if personal_server:
            directory: str= os.getcwd()
            full_path: str = os.path.join(directory, ".venv\\Scripts\\my-mcp-server.exe")
            server_params = StdioServerParameters(command=full_path,args=[],env=None)
        else:
            server_params = StdioServerParameters(command="npx",args=["-y", "@modelcontextprotocol/server-filesystem", root_path])
        
        read,write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        

    async def connect_to_remote_server(self, url:str, headers:dict|None=None):
        read, write, _ = await self.exit_stack.enter_async_context(streamablehttp_client(url=url, headers=headers or {}))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
    

            

    async def chat(self) -> None:
        '''
        Provides chat interface to generate questions and responses
        '''
        history: list[dict] = []
        while True:
            try:
                query = str(input("\nAsk something to chat: ").strip())
                if query == "exit":
                    break
                answer, history = await small_chat(self.session, self.open_ai, query, history=history)
                print("\nAgent: " + answer)
                save_history_jsonl(history=history, path="chat_logs/log.jsonl")
            except KeyboardInterrupt:
                print(f"Session ended by keyboard interruption")
                break

            except Exception as exc:
                print(f"\nError: {exc}")
                break
                
    async def cleanup(self) -> None:
        await self.exit_stack.aclose()




async def main(server_indication:str="filesystem"):
    client = Client()
    try: 
        directory: str= os.getcwd()
        fs_params = StdioServerParameters(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", directory],
                )
        
        full_path: str = os.path.join(directory, ".venv\\Scripts\\my-mcp-server.exe")
        server_params = StdioServerParameters(
                command=full_path,
                args=[],
                env=None
            )
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        if server_indication == "filesystem":
            await client.register_stdio("fs", fs_params)
            await client.register_http(prefix = "gh",url="https://api.githubcopilot.com/mcp/", headers={"Authorization" : f"Bearer {GITHUB_TOKEN}"})
        else:
            await client.connect_to_local_server(personal_server=True)
        # await client.register_http(prefix="cloud", url = "http://18.191.243.65:8000/mcp", headers={})
        await client.chat()
    except * Exception as eg:
        for i, exc in enumerate(eg.exceptions, 1):
            print(f"Excp: {i}: {type(exc).__name__} : {exc}")
            traceback.print_exception(exc)  
    finally:
        await client.cleanup()

def run() -> None:
    print("### Client ###")
    print("Local & Remote | Filesystem & Github")
    indication: str = str(input("Enter mode: "))
    asyncio.run(main(server_indication=indication))

if __name__ == '__main__':
    run()

