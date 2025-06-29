// agent.js
require("dotenv").config();
const axios = require("axios");

// Configuration for FastAPI service
const FASTAPI_URL = process.env.FASTAPI_URL ;

// Function to call FastAPI Python service for task splitting
async function agentExecutor(goal) {
  try {
    console.log(`Sending goal to FastAPI: ${goal}`);
    
    const response = await axios.post(`${FASTAPI_URL}/react-agent`, {
      goal: goal
    }, {
      headers: {
        'Content-Type': 'application/json'
      },
      timeout: 30000 // 30 second timeout
    });

    console.log("FastAPI response:", response.data);
    
    // Return the tasks from FastAPI
    return response.data.tasks;
  } catch (error) {
    console.error("Error calling FastAPI:", error.message);
    
    if (error.response) {
      console.error("FastAPI error response:", error.response.data);
      throw new Error(`FastAPI error: ${error.response.data.error || error.response.statusText}`);
    } else if (error.request) {
      throw new Error("FastAPI service is not responding. Make sure it's running on the correct port.");
    } else {
      throw new Error(`Request setup error: ${error.message}`);
    }
  }
}

module.exports = { agentExecutor };