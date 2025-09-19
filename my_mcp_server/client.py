#
# Reference: https://modelcontextprotocol.io/quickstart/client 

import asyncio, os, traceback
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from dotenv import load_dotenv

load_dotenv() # load environmental variables

class Client:

    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()



    async def connect_to_local_server(self, server_path:str):
        is_python: bool = server_path.endswith('.py')
        is_js: bool = server_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
        
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_path],
            env=None
        )
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()
        
        response = await self.session.list_tools() # gather tools to further get what the Agent needs from the API
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools]) # display tools to user

    async def connect_to_remote_server(self, url:str, headers:dict):

        read, write, _ = await self.exit_stack.enter_async_context(streamablehttp_client(url=url, headers=headers))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()


    
    async def process_query(self, query:str) -> str:
        messages = [
            {
                "role":"user",
                "content":"query"
            }
        ]
        response = await self.session.list_tools()
        available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Initiate API call to Agent 

        # list agent tools 
        final_text = []

        assistant_message_content = []
        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
                assistant_message_content.append(content)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input
                # make tool call
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                assistant_message_content.append(content)
                messages.append({
                    "role": "assistant",
                    "content": assistant_message_content
                })
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": result.content
                        }
                    ]
                })

                # gather Agent API call

                # final_text.append(api_response[0])

        return "\n".join(final_text) # return a string
                

    async def chat(self) -> None:
        '''
        Provides chat interface to generate questions and responses
        '''
        while True:
            try:
                query = input("\nAsk something to chat: ").strip()
                # exit command
                if query.lower() == "exit":
                    break

                response = await self.process_query(query=query)
                print("\n" + response)

            except Exception as exc:
                print(f"\nError: {exc}")
            except KeyboardInterrupt:
                print(f"Session ended by keyboard interruption")

    async def cleanup(self) -> None:
        await self.exit_stack.aclose()


async def main():
    mode: str = "remote"
    client = Client()
    try: 
        if mode == "local":
            server_path = "my_mcp_server/server.py" # path to local server script
            await client.connect_to_local_server(server_path=server_path)
        elif mode == "remote":
            GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
            if not GITHUB_TOKEN:
                raise ValueError("GITHUB_TOKEN not found in environment variables")
            await client.connect_to_remote_server(
                url="https://api.githubcopilot.com/mcp/",
                headers={"Authorization" : f"Bearer {GITHUB_TOKEN}"})
        tools = await client.session.list_tools()
        print("Available tools:", [tool.name for tool in tools.tools])
    except * Exception as eg:
        for i, exc in enumerate(eg.exceptions, 1):
            print(f"Excp: {i}: {type(exc).__name__} : {exc}")
            traceback.print_exception(exc)  
    finally:
        await client.cleanup()

def run() -> None:
    asyncio.run(main())

if __name__ == '__main__':
    run()

