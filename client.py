#
# Reference: https://modelcontextprotocol.io/quickstart/client 

import asyncio
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv() # load environmental variables

class Client:

    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()


    async def connect_to_server(self, server_path:str):
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
                query = input("\nAsk something: ").strip()
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




