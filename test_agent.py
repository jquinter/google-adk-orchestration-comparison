import os
import sys
from dotenv import load_dotenv
sys.path.append(os.path.join(os.getcwd(), 'adk_multiagent_systems'))

# Create a dummy .env if doesn't exist
with open('adk_multiagent_systems/parent_and_subagents/.env', 'w') as f:
    f.write('MODEL=gemini-2.5-flash\n')

from adk_multiagent_systems.parent_and_subagents.agent import app

if __name__ == "__main__":
    response = app.run("Please subtract 10 from 25.")
    print("RESPONSE:", response)
