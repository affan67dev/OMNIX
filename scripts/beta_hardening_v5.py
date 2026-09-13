from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = ROOT / "main.py"
text = main.read_text(encoding="utf-8")
text = text.replace(
    'sender_name = req.sender_name or social_graph.users[current_user_id]["display_name"]',
    'sender_name = req.sender_name or social_graph.users.get(current_user_id, {}).get("display_name", "You")',
)
text = text.replace(
    'actor_name = social_graph.users[current_user_id]["display_name"]',
    'actor_name = social_graph.users.get(current_user_id, {}).get("display_name", "You")',
)
main.write_text(text, encoding="utf-8")
print("beta hardening v5 completed")
