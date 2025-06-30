from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain.agents import Tool, AgentExecutor, create_react_agent
from langchain_community.tools import WikipediaQueryRun
from langchain_experimental.tools.python.tool import PythonREPLTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from pydantic import BaseModel, Field
from typing import List
import os
from dotenv import load_dotenv
import uvicorn
import json
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

load_dotenv()

# Debug: Check if API keys are loaded
print(f"GEMINI_API_KEY loaded: {'Yes' if os.getenv('GEMINI_API_KEY') else 'No'}")
print(f"TAVILY_API_KEY loaded: {'Yes' if os.getenv('TAVILY_API_KEY') else 'No'}")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GoalRequest(BaseModel):
    goal: str

# Define the output structure using Pydantic
class TaskItem(BaseModel):
    step: str = Field(description="The category/phase of the task (e.g., Research, Design, Development, Testing, Deployment)")
    task: str = Field(description="Detailed description of the specific task to be completed")

class TaskList(BaseModel):
    tasks: List[TaskItem] = Field(description="List of actionable subtasks")

# Load LLM with optimized settings
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0,
    max_tokens=2048,  # Limit response length
    timeout=30  # Add timeout for LLM calls
)

# Optimized tools with limited search results
tools = [
    Tool(
        name="Wikipedia",
        func=WikipediaQueryRun(
            api_wrapper=WikipediaAPIWrapper(
                top_k_results=2,  # Limit results
                doc_content_chars_max=1000  # Limit content length
            )
        ).run,
        description="Quick domain background research (use sparingly)"
    ),
    Tool(
        name="WebSearch",
        func=TavilySearchResults(
            api_key=os.getenv("TAVILY_API_KEY"),
            max_results=3  # Limit search results
        ).run,
        description="Quick competitor & market search (use sparingly)"
    )
    # Removed PythonREPLTool to speed up processing
]

# Create the output parser
parser = PydanticOutputParser(pydantic_object=TaskList)

# Create an output fixing parser
fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=llm)

# Simplified and more focused prompt with all required variables
prompt = PromptTemplate.from_template("""
You are an AI Product Manager. Break the user's goal into 5-8 actionable subtasks. Be concise and focused.

You have access to the following tools: {tools}
Tool names: {tool_names}

Use this format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: Return ONLY the JSON object without any markdown formatting or code blocks. {format_instructions}

IMPORTANT: 
- Use tools ONLY if you're unfamiliar with the domain (most goals don't need tools)
- Keep tool usage minimal (max 1-2 tool calls)
- Your final answer must be valid JSON without markdown code blocks
- Focus on 5-8 specific, actionable tasks

Begin!

Question: {input}
Thought: {agent_scratchpad}
""")

prompt = prompt.partial(format_instructions=parser.get_format_instructions())

agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True, 
    handle_parsing_errors=True,
    max_iterations=5,  # Limit iterations
    max_execution_time=45  # 45 second timeout
)

@app.get("/")
async def root():
    return {"message": "FastAPI server is running", "endpoints": ["/react-agent"], "status": "healthy"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "react-agent", "port": 5000}

def extract_json_from_response(text: str) -> str:
    """Improved JSON extraction"""
    if not isinstance(text, str):
        return text
    
    # Remove any markdown formatting
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    
    # Find JSON object
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json_match.group(0)
    
    return text

def run_agent_sync(goal: str):
    """Synchronous wrapper for agent execution"""
    try:
        print(f"Starting agent execution for: {goal}")
        start_time = time.time()
        
        result = agent_executor.invoke({"input": goal})
        
        execution_time = time.time() - start_time
        print(f"Agent execution completed in {execution_time:.2f} seconds")
        
        return result
    except Exception as e:
        print(f"Agent execution failed: {str(e)}")
        raise e

@app.post("/react-agent")
async def run_agent(req: GoalRequest):
    try:
        print(f"Received request: {req.goal}")
        
        # Run agent in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            # Set a 60-second timeout for the entire operation
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, run_agent_sync, req.goal),
                timeout=60.0
            )
        
        print(f"Raw agent result type: {type(result)}")
        output_str = result.get("output", "")
        print(f"Raw output: {output_str[:500]}...")  # Log first 500 chars
        
        # Extract and parse JSON
        cleaned_json = extract_json_from_response(output_str)
        print(f"Cleaned JSON: {cleaned_json[:300]}...")
        
        try:
            # Try direct JSON parsing first
            json_data = json.loads(cleaned_json)
            print("Direct JSON parsing successful")
            
            # Handle different response structures
            if isinstance(json_data, dict) and "tasks" in json_data:
                tasks_data = json_data["tasks"]
            elif isinstance(json_data, list):
                tasks_data = json_data
            else:
                # Try to find tasks in nested structure
                tasks_data = []
                for key, value in json_data.items():
                    if isinstance(value, list) and len(value) > 0:
                        if isinstance(value[0], dict) and ("step" in value[0] or "task" in value[0]):
                            tasks_data = value
                            break
            
            # Convert to TaskItem objects
            task_items = []
            for i, task in enumerate(tasks_data):
                if isinstance(task, dict):
                    task_items.append(TaskItem(
                        step=task.get("step", f"Step {i+1}"),
                        task=task.get("task", task.get("description", "Task description"))
                    ))
                else:
                    # Handle string tasks
                    task_items.append(TaskItem(
                        step=f"Step {i+1}",
                        task=str(task)
                    ))
            
            if not task_items:
                raise ValueError("No valid tasks found in response")
                
            print(f"Successfully parsed {len(task_items)} tasks")
            return {"tasks": task_items}
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {str(e)}")
            # Fallback: try to use the fixing parser
            try:
                parsed_output = fixing_parser.parse(cleaned_json)
                return {"tasks": parsed_output.tasks}
            except Exception as fix_error:
                print(f"Fixing parser also failed: {str(fix_error)}")
                
                # Last resort: create a simple task breakdown
                simple_tasks = [
                    TaskItem(step="Analysis", task="Analyze requirements and define scope"),
                    TaskItem(step="Design", task="Create system design and architecture"),
                    TaskItem(step="Development", task="Implement core functionality"),
                    TaskItem(step="Testing", task="Test and validate the solution"),
                    TaskItem(step="Deployment", task="Deploy and monitor the system")
                ]
                
                return {
                    "tasks": simple_tasks,
                    "warning": "Used fallback task structure due to parsing issues",
                    "raw_output": output_str[:500]
                }
    
    except asyncio.TimeoutError:
        print("Agent execution timed out")
        raise HTTPException(
            status_code=408, 
            detail="Request timed out. The AI agent took too long to process your goal. Try with a simpler goal."
        )
    except Exception as e:
        print(f"Error in agent execution: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)