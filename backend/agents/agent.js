// agent.js
require("dotenv").config();
const { GoogleGenerativeAI } = require("@google/generative-ai");
const axios = require("axios");

// 1. Initialise the SDK with your key
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);



// 3. Export one async function that the server can call
async function agentExecutor(goal) {
  const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });

  const result = await model.generateContent(goal);
  const response = await result.response;
  const text = await response.text();


  return text.trim();
}

module.exports = { agentExecutor };
