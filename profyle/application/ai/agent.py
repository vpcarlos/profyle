import os
import sqlite3
from typing import Any, List

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from profyle.infrastructure.sqlite3.get_connection import get_connection

@tool
def execute_sqlite_query(query: str) -> str:
    """Execute a SQL query against the profile.db SQLite database and return the results.
    The database has a table 'traces' with columns:
    - id (INTEGER PRIMARY KEY)
    - timestamp (TIMESTAMP)
    - duration (REAL)
    - name (VARCHAR)
    - data (JSON) - contains full VizTracer data
    
    Use this tool to inspect traces, find slow traces, and retrieve trace data for analysis.
    Supported SQL only.
    """
    try:
        # Use existing connection logic
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        
        # Fetch results
        if query.strip().upper().startswith("SELECT"):
            columns = [description[0] for description in cursor.description]
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Format as string
            if not results:
                return "No results found."
            
            # Simple formatting
            output = [str(columns)]
            for row in results:
                output.append(str(row))
            return "\n".join(output)
        else:
            # For non-select queries (should not happen mostly)
            conn.commit()
            cursor.close()
            conn.close()
            return "Query executed successfully."
            
    except Exception as e:
        return f"Error executing query: {str(e)}"

class ProfyleAgent:
    _instance = None

    def __init__(self):
        # Initialize Gemini Flash
        api_key = os.getenv("GOOGLE_API_KEY","AIzaSyCiKGVkJ77C_8FD9C9UuRAw6xinncwuAoQ")
        if not api_key:
            print("Warning: GOOGLE_API_KEY not found in environment variables.")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            temperature=0,
            google_api_key=api_key
        )

        self.tools = [execute_sqlite_query]
        
        system_message = """You are an expert Python performance engineer using Profyle. 
You have access to a database of performance traces stored in the 'traces' table via the execute_sqlite_query tool.
The 'traces' table schema is:
CREATE TABLE traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    data JSON NOT NULL,
    duration REAL NOT NULL,
    name VARCHAR(64) NOT NULL
);

Your goal is to help the user analyze these traces to find bottlenecks and improve performance.
1. Start by listing recent traces or summarizing performance metrics (duration) using SQL.
2. If you need to analyze a specific trace, SELECT the 'data' column for that trace ID. 
   The 'data' column contains VizTracer JSON output which has 'traceEvents' with timestamps (ts) and durations (dur).
   Use this data to identify slow function calls.

Always provide specific advice based on the trace data.
If the user asks about Python version or environment, look for it in the trace 'data' (often in metadata events).
"""
        
        # Use create_agent from langchain 1.0+ (graph-based)
        self.agent_executor = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_message
        )

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def run(self, message: str) -> str:
        try:
            # invoke with messages dict
            result = self.agent_executor.invoke({"messages": [HumanMessage(content=message)]})
            
            # The result from create_agent is likely a State dict similar to langgraph
            messages = result.get("messages", [])
            if messages:
                # Get the last message which should be the AI response
                return messages[-1].content
            return "No response generated."
        except Exception as e:
            return f"Error processing request: {str(e)}"

async def get_agent_response(message: str) -> str:
    agent = ProfyleAgent.get_instance()
    # In a real async app, run_in_executor is better for blocking operations
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, agent.run, message)
