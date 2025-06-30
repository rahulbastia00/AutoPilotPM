// agent.js
require("dotenv").config();
const axios = require("axios");

// Configuration for FastAPI service
const FASTAPI_URL = process.env.FASTAPI_URL || "http://localhost:5000";

console.log(`FastAPI URL configured as: ${FASTAPI_URL}`);

// Function to call FastAPI Python service for task splitting
async function agentExecutor(goal) {
  try {
    console.log(`Sending goal to FastAPI: ${goal}`);
    console.log(`FastAPI URL: ${FASTAPI_URL}/react-agent`);

    const response = await axios.post(
      `${FASTAPI_URL}/react-agent`,
      {
        goal: goal,
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
        timeout: 90000, // Increased to 90 seconds for LLM processing
      }
    );

    console.log("FastAPI response status:", response.status);
    console.log(
      "FastAPI response data:",
      JSON.stringify(response.data, null, 2)
    );

    // Check if response has tasks
    if (!response.data || !response.data.tasks) {
      console.warn("No tasks found in response, returning empty array");
      return [];
    }

    // Return the tasks from FastAPI
    return response.data.tasks;
  } catch (error) {
    console.error("Error calling FastAPI:", error.message);

    if (error.code === "ECONNREFUSED") {
      console.error("Connection refused - FastAPI server might not be running");
      throw new Error(
        "FastAPI service is not running. Please start the Python server on port 5000."
      );
    }

    if (error.code === "ETIMEDOUT") {
      console.error(
        "Request timed out - FastAPI is taking too long to respond"
      );
      throw new Error(
        "FastAPI service timed out. The LLM might be taking too long to process."
      );
    }

    if (error.response) {
      console.error("FastAPI error response status:", error.response.status);
      console.error("FastAPI error response data:", error.response.data);
      throw new Error(
        `FastAPI error (${error.response.status}): ${
          error.response.data.detail || error.response.statusText
        }`
      );
    } else if (error.request) {
      console.error("No response received from FastAPI");
      throw new Error(
        "FastAPI service is not responding. Make sure it's running on the correct port."
      );
    } else {
      console.error("Request setup error:", error.message);
      throw new Error(`Request setup error: ${error.message}`);
    }
  }
}

// Test function to check FastAPI connectivity
async function testFastAPIConnection() {
  try {
    console.log("Testing FastAPI connection...");
    const response = await axios.get(`${FASTAPI_URL}/health`, {
      timeout: 5000,
    });
    console.log("FastAPI health check successful:", response.data);
    return true;
  } catch (error) {
    console.error("FastAPI health check failed:", error.message);
    return false;
  }
}

module.exports = { agentExecutor, testFastAPIConnection };
