import subprocess
import sys
import os

def run_adk_agent(agent_path, query):
    """Run an ADK agent via the CLI and return the stdout."""
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    cmd = [".venv/bin/adk", "run", agent_path, query]
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env
    )
    
    if result.returncode != 0:
        print(f"Error running agent: {result.stderr}", file=sys.stderr)
        return None, result.returncode
        
    return result.stdout, result.returncode

def main():
    test_cases = [
        {
            "name": "Multi-agent Calculator (parent_and_subagents)",
            "path": "adk_multiagent_systems/parent_and_subagents",
            "query": "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5)",
            "expected": "109"
        },
        {
            "name": "Workflow-based Calculator (workflow_agents)",
            "path": "adk_multiagent_systems/workflow_agents",
            "query": "((12 + 8) * 5) - (10 / 2) + (4 * 6) - (50 / 5)",
            "expected": "109"
        },
        {
            "name": "Multi-agent Zero-Division Guard",
            "path": "adk_multiagent_systems/parent_and_subagents",
            "query": "Please evaluate 10 / 0",
            "expected": "División por cero detectada"
        },
        {
            "name": "Workflow-based Zero-Division Guard",
            "path": "adk_multiagent_systems/workflow_agents",
            "query": "Please evaluate 10 / 0",
            "expected": "División por cero detectada"
        }
    ]

    all_passed = True
    print("==================================================")
    print(" RUNNING SYSTEM INTEGRATION TESTS")
    print("==================================================\n")

    for case in test_cases:
        print(f"--- Testing: {case['name']} ---")
        output, code = run_adk_agent(case['path'], case['query'])
        
        if output is None:
            print(f"❌ FAIL: Command execution failed with code {code}\n")
            all_passed = False
            continue
            
        print("Agent Output:")
        print(output.strip())
        
        # Check if the expected result is in the output text
        if case['expected'] in output:
            print(f"✅ PASS: Found expected result '{case['expected']}' in the output.\n")
        else:
            print(f"❌ FAIL: Expected result '{case['expected']}' NOT found in the output.\n")
            all_passed = False

    print("==================================================")
    if all_passed:
        print("🎉 ALL TESTS PASSED SUCCESSFULLY! 🎉")
        sys.exit(0)
    else:
        print("🚨 SOME TESTS FAILED. Please review the output above. 🚨")
        sys.exit(1)

if __name__ == "__main__":
    main()
