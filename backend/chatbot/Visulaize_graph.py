"""
Visualizes the LangGraph Multi-Node Workflow.
Generates:
1. Agent_Workflow.png (Image diagram via mermaid service)
2. Agent_Workflow.mmd (Mermaid diagram code that you can preview anywhere or in VS Code/Mermaid Live)
"""

import os
import sys
from pathlib import Path

# Ensure backend root is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import the COMPILED agent, not the uncompiled workflow
# from chatbot.agent_multi_node import agent
from chatbot.customer_agent import agent

current_dir = Path(__file__).resolve().parent
png_output_path = current_dir / "Agent_Workflow6.png"
mmd_output_path = current_dir / "Agent_Workflow6.mmd"

# 1. Get Mermaid syntax string
mermaid_text = agent.get_graph().draw_mermaid()
with open(mmd_output_path, "w", encoding="utf-8") as f:
    f.write(mermaid_text)
print(f"✅ Mermaid code saved to: {mmd_output_path}")

# 2. Render to PNG image
try:
    png_bytes = agent.get_graph().draw_mermaid_png()
    with open(png_output_path, "wb") as f:
        f.write(png_bytes)
    print(f"🎉 Graph image successfully saved as: {png_output_path}")
except Exception as e:
    print(f"⚠️ Could not render remote PNG (likely network or mermaid API access): {e}")
    print("💡 You can copy the code from Agent_Workflow.mmd into https://mermaid.live to see the diagram instantly!")