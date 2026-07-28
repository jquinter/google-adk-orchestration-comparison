import sqlite3
import json
import os
import sys

def main():
    db_path = 'adk_multiagent_systems/workflow_agents/.adk/session.db'
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the latest invocation ID
    cursor.execute("SELECT DISTINCT invocation_id, timestamp FROM events ORDER BY timestamp DESC LIMIT 1;")
    row = cursor.fetchone()
    if not row:
        print("No invocations found in the database.", file=sys.stderr)
        return
    
    latest_invocation_id = row['invocation_id']
    
    # Query all events for the latest invocation id ordered by timestamp ascending
    cursor.execute(
        "SELECT event_data FROM events WHERE invocation_id = ? ORDER BY timestamp ASC;",
        (latest_invocation_id,)
    )
    rows = cursor.fetchall()
    
    print(f"\n======================================================================")
    print(f" TIMELINE FOR INVOCATION: {latest_invocation_id}")
    print(f"======================================================================\n")

    step_counter = 1
    
    for row in rows:
        event = json.loads(row['event_data'])
        author = event.get('author', 'unknown')
        content = event.get('content', {})
        parts = content.get('parts', [])
        
        # 1. Parse content parts (text, function calls, function responses)
        text_content = []
        function_calls = []
        function_responses = []
        
        for part in parts:
            if 'text' in part and part['text'].strip():
                text_content.append(part['text'].strip())
            if 'function_call' in part:
                function_calls.append(part['function_call'])
            if 'function_response' in part:
                function_responses.append(part['function_response'])
                
        # 2. Render beautifully depending on the type of event
        if author == 'user':
            is_framework_context = False
            for text in text_content:
                if text.startswith('For context:') or text.startswith('[') and ']' in text:
                    is_framework_context = True
            
            if is_framework_context:
                for text in text_content:
                    if not text.startswith('For context:'):
                        print(f" ⚙️  [System/Context]: {text}")
                continue
            
            user_text = " ".join(text_content)
            print(f"\n👤 [User]: {user_text}")
            print("-" * 70)
        else:
            agent_header = f"🤖 [{author.upper()}]"
            
            if text_content:
                text_block = "\n".join(text_content)
                print(f"{agent_header}:")
                for line in text_block.split('\n'):
                    print(f"   {line}")
            
            for fc in function_calls:
                name = fc.get('name')
                args = fc.get('args', {})
                args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
                print(f"⚡ {agent_header} calls tool: {name}({args_str})")
            
            print("-" * 70)
            step_counter += 1

    print("\n======================================================================")

if __name__ == '__main__':
    main()
