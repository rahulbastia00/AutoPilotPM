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
import os
from dotenv import load_dotenv
import uvicorn

load_dotenv()

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

# Load LLM and tools once
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0
)

tools = [
    Tool(
        name="Wikipedia",
        func=WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()).run,
        description="Domain background research"
    ),
    Tool(
        name="WebSearch",
        func=TavilySearchResults(api_key=os.getenv("TAVILY_API_KEY")).run,
        description="Competitor & market search"
    ),
    PythonREPLTool()
]

prompt = PromptTemplate.from_template("""
You are an AI Product Manager. Break the user's goal into actionable subtasks. Think step-by-step. Use the tools when helpful.

You have access to the following tools: {tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: Return a JSON array like:
[
  {{"step": "Research", "task": "..."}},
  {{"step": "Design",  "task": "..."}},
  ...
]

Begin!

Question: {input}
Thought: {agent_scratchpad}
""")

agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

@app.get("/")
async def root():
    return {"message": "FastAPI server is running", "endpoints": ["/react-agent"]}

@app.post("/react-agent")
async def run_agent(req: GoalRequest):
    try:
        print(f"Received request: {req.goal}")
        result = agent_executor.invoke({"input": req.goal})
        print(f"Agent result: {result}")
        return {"tasks": result["output"]}
    except Exception as e:
        print(f"Error in agent execution: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)