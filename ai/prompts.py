from typing import Dict


SYSTEM_PROMPT = """You are an offline AI coding assistant for a Windows desktop IDE.\nYou help with coding, debugging, explaining code, creating files, and scaffolding projects.\nAlways prefer concise, practical answers.\n"""


def build_context_prompt(files: list[str], user_request: str) -> str:
    file_list = "\n".join(files[:20])
    return f"""You are working with the following project files:\n{file_list}\n\nUser request:\n{user_request}\n"""
