from chainbreaker.agent import loop


def test_chat_store_keeps_history_per_dataset_and_caps():
    cid, chat = loop._load_chat("demo", None)
    chat["messages"].append({"role": "user", "content": "q1"})
    loop._save_chat(cid, chat)
    same, again = loop._load_chat("demo", cid)
    assert same == cid and again["messages"] == [{"role": "user", "content": "q1"}]
    other, fresh = loop._load_chat("cncf", cid)  # a chat never crosses datasets
    assert other != cid and fresh["messages"] == []
    for i in range(loop.MAX_CHATS + 5):
        loop._save_chat(f"c{i}", {"ds": "demo", "messages": [], "known": []})
    assert len(loop._chats) == loop.MAX_CHATS and cid not in loop._chats
