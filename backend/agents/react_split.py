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

# Enhanced task structure with more detailed fields
class TaskItem(BaseModel):
    step: str = Field(description="The category/phase of the task")
    task: str = Field(description="Brief title of the task")
    description: str = Field(description="Detailed description of what needs to be done")
    technologies: List[str] = Field(description="Recommended technologies/tools for this task")
    deliverables: List[str] = Field(description="Expected outputs/deliverables from this task")
    estimated_time: str = Field(description="Estimated time to complete this task")

class TaskList(BaseModel):
    tasks: List[TaskItem] = Field(description="List of detailed actionable subtasks")

# Load LLM with optimized settings for more detailed responses
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.1,  # Slightly higher for more creative responses
    max_tokens=4096,  # Increased for more detailed responses
    timeout=45  # Increased timeout
)

# Re-enable tools with better error handling
tools = [
    Tool(
        name="Wikipedia",
        func=WikipediaQueryRun(
            api_wrapper=WikipediaAPIWrapper(
                top_k_results=2,
                doc_content_chars_max=800
            )
        ).run,
        description="Research domain knowledge and technical concepts"
    ),
    Tool(
        name="WebSearch",
        func=TavilySearchResults(
            api_key=os.getenv("TAVILY_API_KEY"),
            max_results=2
        ).run,
        description="Search for current best practices and technologies"
    )
]

# Create the output parser
parser = PydanticOutputParser(pydantic_object=TaskList)

# Enhanced prompt template for ReAct agent with tools
prompt_template = """
You are an expert AI Product Manager and Technical Architect. Break down complex project goals into detailed, actionable tasks with specific technical guidance.

You have access to these tools: {tools}
Tool names: {tool_names}

Use this format:
Question: the input question you must answer
Thought: think about what you need to do - consider if you need to research current technologies or best practices
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now have enough information to provide detailed tasks
Final Answer: Provide a JSON object with detailed tasks

For the final answer, create 6-8 comprehensive tasks in this JSON format:
{{
  "tasks": [
    {{
      "step": "Phase name",
      "task": "Brief task title", 
      "description": "Detailed explanation with specific steps",
      "technologies": ["Technology 1", "Technology 2"],
      "deliverables": ["Deliverable 1", "Deliverable 2"],
      "estimated_time": "Time estimate"
    }}
  ]
}}

IMPORTANT:
- Use tools ONLY if you need to research unfamiliar domains or current best practices
- Keep tool usage minimal (max 2 tool calls)
- Focus on actionable, technology-specific tasks
- Include implementation details and considerations
- Provide realistic time estimates

Begin!
Question: {input}
Thought: {agent_scratchpad}"""

def generate_detailed_tasks(goal: str) -> dict:
    """Generate detailed tasks using ReAct agent with tools"""
    try:
        print(f"Generating detailed tasks for: {goal}")
        start_time = time.time()
        
        # Create ReAct agent with tools
        prompt = PromptTemplate.from_template(prompt_template)
        agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=4,  # Reduced iterations
            max_execution_time=40  # Reduced timeout
        )
        
        # Execute agent
        result = agent_executor.invoke({"input": goal})
        
        execution_time = time.time() - start_time
        print(f"Task generation completed in {execution_time:.2f} seconds")
        
        return result
    except Exception as e:
        print(f"Task generation with tools failed: {str(e)}")
        # Fallback to direct LLM call without tools
        try:
            print("Falling back to direct LLM call without tools")
            simple_prompt = f"""
            Create 6-8 detailed project tasks for: {goal}
            
            Respond with JSON in this format:
            {{
              "tasks": [
                {{
                  "step": "Phase name",
                  "task": "Task title",
                  "description": "Detailed description with specific steps",
                  "technologies": ["Tech1", "Tech2"],
                  "deliverables": ["Deliverable1", "Deliverable2"],
                  "estimated_time": "Time estimate"
                }}
              ]
            }}
            """
            response = llm.invoke(simple_prompt)
            return {"output": response.content}
        except Exception as fallback_error:
            print(f"Fallback also failed: {str(fallback_error)}")
            raise e

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

def create_fallback_tasks(goal: str) -> List[TaskItem]:
    """Create detailed fallback tasks based on the goal"""
    
    # Analyze goal to determine project type
    goal_lower = goal.lower()
    
    if any(keyword in goal_lower for keyword in ['mobile', 'app', 'ios', 'android']):
        return [
            TaskItem(
                step="Requirements Analysis",
                task="Define Functional and Non-Functional Requirements",
                description="Conduct stakeholder interviews, create user stories, define MVP features, and document technical requirements. Create a comprehensive requirements document including user personas, use cases, and acceptance criteria.",
                technologies=["Figma", "Jira", "Confluence", "User Story Mapping Tools"],
                deliverables=["Requirements Document", "User Stories", "MVP Feature List", "Technical Specifications"],
                estimated_time="1-2 weeks"
            ),
            TaskItem(
                step="Technical Architecture",
                task="Design System Architecture and Technology Stack",
                description="Design the overall system architecture, choose technology stack, plan database schema, and define API structure. Consider scalability, security, and maintainability requirements.",
                technologies=["React Native/Flutter", "Node.js/Python", "PostgreSQL/MongoDB", "AWS/Firebase", "REST/GraphQL"],
                deliverables=["Architecture Diagram", "Technology Stack Document", "Database Schema", "API Documentation"],
                estimated_time="1-2 weeks"
            ),
            TaskItem(
                step="UI/UX Design",
                task="Create User Interface and Experience Design",
                description="Design wireframes, create high-fidelity mockups, develop design system, and create interactive prototypes. Ensure responsive design and accessibility compliance.",
                technologies=["Figma", "Adobe XD", "Sketch", "InVision", "Design System Tools"],
                deliverables=["Wireframes", "High-fidelity Mockups", "Design System", "Interactive Prototype"],
                estimated_time="2-3 weeks"
            ),
            TaskItem(
                step="Backend Development",
                task="Develop Server-Side Logic and APIs",
                description="Set up development environment, implement authentication, create REST/GraphQL APIs, integrate with third-party services, and implement business logic with proper error handling and security measures.",
                technologies=["Node.js/Express", "Python/Django", "JWT", "Stripe/PayPal APIs", "AWS S3", "Redis"],
                deliverables=["API Endpoints", "Authentication System", "Database Models", "Third-party Integrations"],
                estimated_time="4-6 weeks"
            ),
            TaskItem(
                step="Frontend Development",
                task="Build Mobile Application Interface",
                description="Implement UI components, integrate with backend APIs, implement navigation, add state management, and ensure cross-platform compatibility with native features integration.",
                technologies=["React Native", "Flutter", "Redux/MobX", "Native Modules", "Push Notifications"],
                deliverables=["Mobile App Components", "API Integration", "Navigation System", "State Management"],
                estimated_time="4-6 weeks"
            ),
            TaskItem(
                step="Testing & Quality Assurance",
                task="Comprehensive Testing and Bug Fixing",
                description="Implement unit tests, integration tests, perform manual testing on multiple devices, conduct security testing, and optimize performance. Include accessibility testing and user acceptance testing.",
                technologies=["Jest", "Detox", "Appium", "Firebase Test Lab", "Security Testing Tools"],
                deliverables=["Test Suites", "Test Reports", "Performance Metrics", "Bug Fix Documentation"],
                estimated_time="2-3 weeks"
            ),
            TaskItem(
                step="Deployment & Launch",
                task="Deploy to App Stores and Production",
                description="Set up CI/CD pipeline, prepare app store listings, deploy backend to production servers, submit apps for review, and configure monitoring and analytics systems.",
                technologies=["GitHub Actions", "App Store Connect", "Google Play Console", "AWS/Heroku", "Analytics Tools"],
                deliverables=["Published Apps", "Production Environment", "CI/CD Pipeline", "Monitoring Dashboard"],
                estimated_time="1-2 weeks"
            )
        ]
    
    # Default fallback for web/general projects
    return [
        TaskItem(
            step="Project Planning",
            task="Define Project Scope and Requirements",
            description="Analyze the project requirements, define the scope, create user stories, and establish project timeline. Conduct stakeholder meetings and document all functional and non-functional requirements.",
            technologies=["Project Management Tools", "Documentation Platforms", "Requirement Analysis Tools"],
            deliverables=["Project Scope Document", "User Stories", "Timeline", "Requirements Specification"],
            estimated_time="1-2 weeks"
        ),
        TaskItem(
            step="System Design",
            task="Create Technical Architecture and Design",
            description="Design the system architecture, choose appropriate technology stack, create database schema, and plan API structure. Consider scalability, security, and performance requirements.",
            technologies=["System Design Tools", "Database Design Tools", "API Documentation Tools"],
            deliverables=["Architecture Diagram", "Database Schema", "API Design", "Technology Stack Selection"],
            estimated_time="1-2 weeks"
        ),
        TaskItem(
            step="Development Setup",
            task="Set Up Development Environment and Infrastructure",
            description="Set up development environment, configure version control, establish coding standards, and prepare deployment infrastructure. Include security configurations and monitoring setup.",
            technologies=["Git", "Docker", "CI/CD Tools", "Cloud Platforms", "Development IDEs"],
            deliverables=["Development Environment", "Git Repository", "Deployment Pipeline", "Coding Standards Document"],
            estimated_time="3-5 days"
        ),
        TaskItem(
            step="Core Development",
            task="Implement Core Functionality",
            description="Develop the main features and functionality of the application. Implement business logic, user authentication, data management, and core user workflows with proper error handling.",
            technologies=["Programming Languages", "Frameworks", "Databases", "Authentication Systems"],
            deliverables=["Core Application Features", "Authentication System", "Database Implementation", "API Endpoints"],
            estimated_time="4-8 weeks"
        ),
        TaskItem(
            step="Testing & QA",
            task="Test and Validate the System",
            description="Perform comprehensive testing including unit tests, integration tests, performance testing, and security testing. Conduct user acceptance testing and fix identified issues.",
            technologies=["Testing Frameworks", "Automated Testing Tools", "Performance Testing Tools", "Security Testing Tools"],
            deliverables=["Test Suites", "Test Reports", "Performance Metrics", "Security Assessment"],
            estimated_time="2-3 weeks"
        ),
        TaskItem(
            step="Deployment",
            task="Deploy to Production Environment",
            description="Deploy the application to production servers, configure monitoring and logging, set up backup systems, and ensure high availability. Include performance optimization and security hardening.",
            technologies=["Cloud Platforms", "Monitoring Tools", "Backup Solutions", "Security Tools"],
            deliverables=["Production Deployment", "Monitoring Dashboard", "Backup System", "Security Configuration"],
            estimated_time="1-2 weeks"
        )
    ]

def run_task_generation_sync(goal: str):
    """Synchronous wrapper for task generation"""
    try:
        print(f"Starting task generation for: {goal}")
        result = generate_detailed_tasks(goal)
        return result
    except Exception as e:
        print(f"Task generation failed: {str(e)}")
        raise e

@app.post("/react-agent")
async def run_agent(req: GoalRequest):
    try:
        print(f"Received request: {req.goal}")
        
        # Run task generation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            # Set a 60-second timeout for the entire operation
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, run_task_generation_sync, req.goal),
                timeout=60.0
            )
        
        print(f"Raw result type: {type(result)}")
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
                raise ValueError("Invalid JSON structure")
            
            # Convert to TaskItem objects with enhanced validation
            task_items = []
            for i, task in enumerate(tasks_data):
                if isinstance(task, dict):
                    task_items.append(TaskItem(
                        step=task.get("step", f"Step {i+1}"),
                        task=task.get("task", "Task"),
                        description=task.get("description", task.get("task", "Task description")),
                        technologies=task.get("technologies", []),
                        deliverables=task.get("deliverables", []),
                        estimated_time=task.get("estimated_time", "TBD")
                    ))
            
            if not task_items:
                raise ValueError("No valid tasks found in response")
                
            print(f"Successfully parsed {len(task_items)} detailed tasks")
            return {"tasks": task_items}
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"JSON parsing failed: {str(e)}")
            
            # Fallback: create detailed tasks based on goal analysis
            print("Using intelligent fallback task generation")
            fallback_tasks = create_fallback_tasks(req.goal)
            
            return {
                "tasks": fallback_tasks,
                "note": "Generated using intelligent task analysis"
            }
    
    except asyncio.TimeoutError:
        print("Task generation timed out")
        raise HTTPException(
            status_code=408, 
            detail="Request timed out. Please try with a simpler goal."
        )
    except Exception as e:
        print(f"Error in task generation: {str(e)}")
        # Last resort fallback
        fallback_tasks = create_fallback_tasks(req.goal)
        return {
            "tasks": fallback_tasks,
            "note": "Generated using fallback task analysis due to processing error"
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)