import hashlib
import json
import threading
import tkinter as tk
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import Canvas, Frame

import requests

API_URL = "http://127.0.0.1:8000/ask"
ADMIN_DASHBOARD_URL = "http://127.0.0.1:8000/admin/dashboard"
TRACK_LOGIN_URL = "http://127.0.0.1:8000/track-login"
CHAT_STORE = Path("chat_history.json")
USERS_STORE = Path("users.json")
ADMIN_USER_ID = "admin"
ADMIN_PASSWORD = "123"

# ============================
# Soft Glass Theme
# ============================
BG_APP = "#edf4ef"
BG_SIDEBAR = "#e5efe8"
BG_SURFACE = "#f8fbf8"
BG_HEADER = "#edf6ef"
ACCENT = "#1f6f5f"
ACCENT_HOVER = "#2a8774"
USER_BUBBLE = "#eef5ef"
USER_TEXT = "#19352f"
BOT_BUBBLE = "#ffffff"
BOT_TEXT = "#202b29"
TITLE_TEXT = "#16231f"
PRIMARY_TEXT = "#31423d"
MUTED_TEXT = "#6a7874"
BORDER_COLOR = "#d6e2da"
INPUT_BG = "#fdfefd"
INPUT_FG = "#1f2a28"
PLACEHOLDER = "#90a09a"
SIDEBAR_ACTIVE = "#d9e9df"
ERROR_TEXT = "#b42318"
SUCCESS_TEXT = "#116329"
CARD_SHADOW = "#dfe9e2"
PROMPT_CARD = "#f2f7f3"
PROMPT_CARD_HOVER = "#e7f1eb"

FONT_FAMILY = "Segoe UI"

conversations = []
current_conversation_id = None
current_user_id = None
typing_frame = None
typing_label = None
typing_dots_state = 0
typing_after_id = None
prompt_buttons = []


def now_iso() -> str:
    return datetime.now().isoformat()


def display_timestamp(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%I:%M %p")
    except Exception:
        return value


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users():
    if not USERS_STORE.exists():
        return {}
    try:
        return json.loads(USERS_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_users(users):
    USERS_STORE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def load_chat_store():
    if not CHAT_STORE.exists():
        return {"users": {}}
    try:
        payload = json.loads(CHAT_STORE.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return {"users": {"legacy": payload}}
        if "users" not in payload:
            payload["users"] = {}
        return payload
    except Exception:
        return {"users": {}}


def save_chat_store(store):
    CHAT_STORE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def load_conversations():
    if not current_user_id:
        return []
    store = load_chat_store()
    return store["users"].get(current_user_id, [])


def save_conversations():
    if not current_user_id:
        return
    store = load_chat_store()
    store["users"][current_user_id] = conversations
    save_chat_store(store)


def conversation_title(message: str) -> str:
    trimmed = " ".join(message.strip().split())
    if not trimmed:
        return "New chat"
    return trimmed[:40] + ("..." if len(trimmed) > 40 else "")


def create_conversation(initial_message: str = ""):
    title = conversation_title(initial_message) if initial_message else "New chat"
    conversation = {
        "id": str(uuid.uuid4()),
        "title": title,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "messages": [],
    }
    conversations.insert(0, conversation)
    save_conversations()
    refresh_sidebar()
    return conversation


def get_current_conversation():
    for conversation in conversations:
        if conversation["id"] == current_conversation_id:
            return conversation
    return None


def ensure_current_conversation():
    global current_conversation_id
    conversation = get_current_conversation()
    if conversation:
        return conversation
    if conversations:
        current_conversation_id = conversations[0]["id"]
        return conversations[0]
    conversation = create_conversation()
    current_conversation_id = conversation["id"]
    return conversation


def add_message_to_current(sender: str, text: str):
    conversation = ensure_current_conversation()
    if not conversation["messages"] and sender == "user":
        conversation["title"] = conversation_title(text)
    conversation["messages"].append(
        {"sender": sender, "text": text, "created_at": now_iso()}
    )
    conversation["updated_at"] = now_iso()
    conversations.sort(key=lambda item: item["updated_at"], reverse=True)
    save_conversations()
    refresh_sidebar()


def refresh_sidebar():
    if not conversation_list.winfo_exists():
        return

    conversation_list.delete(0, tk.END)
    for conversation in conversations:
        conversation_list.insert(tk.END, conversation["title"])

    user_display.config(text=f"User ID: {current_user_id}" if current_user_id else "Not logged in")
    if "avatar_badge" in globals() and avatar_badge.winfo_exists():
        avatar_badge.config(text=(current_user_id[:1].upper() if current_user_id else "U"))

    if not conversations:
        return

    for index, conversation in enumerate(conversations):
        conversation_list.itemconfig(index, bg=BG_SIDEBAR, fg=PRIMARY_TEXT)
        if conversation["id"] == current_conversation_id:
            conversation_list.itemconfig(index, bg=SIDEBAR_ACTIVE, fg=TITLE_TEXT)
            conversation_list.selection_clear(0, tk.END)
            conversation_list.selection_set(index)


def clear_chat_area():
    global typing_frame, typing_label, typing_after_id
    if typing_after_id:
        root.after_cancel(typing_after_id)
        typing_after_id = None
    typing_frame = None
    typing_label = None
    for widget in chat_frame.winfo_children():
        widget.destroy()


def set_entry_text(text: str):
    global _has_placeholder
    entry.delete(0, tk.END)
    entry.insert(0, text)
    entry.configure(fg=INPUT_FG)
    _has_placeholder = False
    entry.focus_set()


def create_prompt_card(parent, title: str, command_text: str):
    card = Frame(parent, bg=PROMPT_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
    card.pack(side="left", fill="both", expand=True, padx=6)

    label = tk.Label(
        card,
        text=title,
        bg=PROMPT_CARD,
        fg=PRIMARY_TEXT,
        justify="left",
        wraplength=170,
        font=(FONT_FAMILY, 11),
        padx=14,
        pady=14,
        cursor="hand2",
    )
    label.pack(fill="both", expand=True)

    def on_enter(_event):
        card.configure(bg=PROMPT_CARD_HOVER)
        label.configure(bg=PROMPT_CARD_HOVER)

    def on_leave(_event):
        card.configure(bg=PROMPT_CARD)
        label.configure(bg=PROMPT_CARD)

    def on_click(_event):
        set_entry_text(command_text)

    for widget in (card, label):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        widget.bind("<Button-1>", on_click)

    prompt_buttons.append(card)


def render_welcome():
    shell = Frame(chat_frame, bg=BG_APP)
    shell.pack(fill="both", expand=True, pady=(34, 24))

    welcome_frame = Frame(shell, bg=BG_SURFACE, highlightbackground=CARD_SHADOW, highlightthickness=1)
    welcome_frame.pack(padx=80, ipadx=20, ipady=20)

    top_orb = tk.Label(
        welcome_frame,
        text="●",
        bg=BG_SURFACE,
        fg="#6ddf67",
        font=("Segoe UI Symbol", 44),
    )
    top_orb.pack(pady=(24, 6))

    greeting = tk.Label(
        welcome_frame,
        text=f"Good evening, {current_user_id or 'User'}",
        bg=BG_SURFACE,
        fg=TITLE_TEXT,
        font=(FONT_FAMILY, 16, "bold"),
    )
    greeting.pack()

    welcome_text = tk.Label(
        welcome_frame,
        text="Can I help you with anything?",
        bg=BG_SURFACE,
        fg=TITLE_TEXT,
        font=(FONT_FAMILY, 22, "bold"),
    )
    welcome_text.pack(pady=(4, 10))

    welcome_sub = tk.Label(
        welcome_frame,
        text="Choose a prompt below or write your own to start chatting with TerraLaw BD.",
        bg=BG_SURFACE,
        fg=MUTED_TEXT,
        font=(FONT_FAMILY, 11),
        wraplength=430,
        justify="center",
    )
    welcome_sub.pack(pady=(0, 24))

    prompt_row = Frame(welcome_frame, bg=BG_SURFACE)
    prompt_row.pack(fill="x", padx=20)

    create_prompt_card(
        prompt_row,
        "Can a co-sharer claim pre-emption after a sale?",
        "My father sold part of our family land to an outsider without informing the other co-sharers. Can I claim pre-emption, and what documents would I need?",
    )
    create_prompt_card(
        prompt_row,
        "What should I do after an acquisition notice?",
        "The government published a notice saying our land may be acquired for a public purpose. How can we object, within how many days, and before which authority?",
    )

    refresh_prompts = tk.Label(
        welcome_frame,
        text="Use a prompt card or type your own question below.",
        bg=BG_SURFACE,
        fg=MUTED_TEXT,
        font=(FONT_FAMILY, 10),
    )
    refresh_prompts.pack(anchor="w", padx=24, pady=(18, 4))


def load_conversation(conversation_id: str):
    global current_conversation_id
    current_conversation_id = conversation_id
    clear_chat_area()

    conversation = ensure_current_conversation()
    if not conversation["messages"]:
        render_welcome()
    else:
        for message in conversation["messages"]:
            add_bubble(
                message["text"],
                message["sender"],
                timestamp=display_timestamp(message["created_at"]),
                persist=False,
            )

    refresh_sidebar()
    canvas.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))
    canvas.yview_moveto(1.0)


def start_new_chat():
    global current_conversation_id
    conversation = create_conversation()
    current_conversation_id = conversation["id"]
    load_conversation(current_conversation_id)


def on_conversation_select(event=None):
    selection = conversation_list.curselection()
    if not selection:
        return
    conversation = conversations[selection[0]]
    load_conversation(conversation["id"])


def send_message(event=None):
    if not current_user_id:
        return

    message = entry.get().strip()
    if not message or message == PLACEHOLDER_TEXT:
        return

    entry.delete(0, tk.END)
    show_placeholder()
    add_bubble(message, "user")
    show_typing_indicator()

    threading.Thread(target=process_reply, args=(message,), daemon=True).start()


def process_reply(msg):
    try:
        response = requests.get(API_URL, params={"question": msg}, timeout=60)
        response.raise_for_status()
        try:
            data = response.json()
            answer = format_response(data)
        except ValueError:
            answer = response.text.strip() or "No response received."
    except Exception as exc:
        answer = f"Connection error: {exc}"

    root.after(0, _on_reply, answer)


def track_login_event(user_id: str, role: str):
    try:
        requests.get(
            TRACK_LOGIN_URL,
            params={"user_id": user_id, "role": role},
            timeout=5,
        )
    except Exception:
        pass


def _on_reply(answer):
    hide_typing_indicator()
    add_bubble(answer, "assistant")


def format_response(data):
    return data.get("answer", "No response received.")


def add_bubble(text, sender, timestamp=None, persist=True):
    if persist:
        add_message_to_current(sender, text)

    stamp = timestamp or datetime.now().strftime("%I:%M %p")
    row = Frame(chat_frame, bg=BG_APP)

    is_user = sender == "user"
    anchor = "e" if is_user else "w"
    label_text = "You" if is_user else "Assistant"
    bubble_bg = USER_BUBBLE if is_user else BOT_BUBBLE
    bubble_fg = USER_TEXT if is_user else BOT_TEXT

    meta_frame = Frame(row, bg=BG_APP)
    meta_frame.pack(anchor=anchor, padx=18, pady=(6, 0))

    sender_label = tk.Label(
        meta_frame,
        text=label_text,
        bg=BG_APP,
        fg=ACCENT if is_user else MUTED_TEXT,
        font=(FONT_FAMILY, 9, "bold"),
    )
    sender_label.pack(side="left")

    time_label = tk.Label(
        meta_frame,
        text=f"  |  {stamp}",
        bg=BG_APP,
        fg=MUTED_TEXT,
        font=(FONT_FAMILY, 8),
    )
    time_label.pack(side="left")

    bubble_container = Frame(
        row,
        bg=bubble_bg,
        padx=1,
        pady=1,
        highlightbackground=BORDER_COLOR,
        highlightthickness=1,
    )
    bubble_container.pack(anchor=anchor, padx=22, pady=(2, 8))

    bubble_inner = Frame(bubble_container, bg=bubble_bg)
    bubble_inner.pack(padx=16, pady=12)

    msg_label = tk.Label(
        bubble_inner,
        text=text,
        bg=bubble_bg,
        fg=bubble_fg,
        wraplength=520,
        justify="left",
        font=(FONT_FAMILY, 11),
        anchor="w",
    )
    msg_label.pack(anchor="w")

    row.pack(fill="x", pady=1)

    canvas.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))
    canvas.yview_moveto(1.0)


def show_typing_indicator():
    global typing_frame, typing_label, typing_dots_state, typing_after_id

    if typing_frame:
        return

    typing_frame = Frame(chat_frame, bg=BG_APP)

    meta = Frame(typing_frame, bg=BG_APP)
    meta.pack(anchor="w", padx=18, pady=(6, 0))
    tk.Label(meta, text="Assistant", bg=BG_APP, fg=MUTED_TEXT,
             font=(FONT_FAMILY, 9, "bold")).pack(side="left")

    dot_container = Frame(
        typing_frame,
        bg=BOT_BUBBLE,
        padx=1,
        pady=1,
        highlightbackground=BORDER_COLOR,
        highlightthickness=1,
    )
    dot_container.pack(anchor="w", padx=22, pady=(2, 8))

    dot_inner = Frame(dot_container, bg=BOT_BUBBLE)
    dot_inner.pack(padx=14, pady=10)

    typing_label = tk.Label(
        dot_inner,
        text=". . .",
        bg=BOT_BUBBLE,
        fg=MUTED_TEXT,
        font=(FONT_FAMILY, 12),
    )
    typing_label.pack()

    typing_frame.pack(fill="x", pady=1)
    typing_dots_state = 0
    _animate_typing()

    canvas.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))
    canvas.yview_moveto(1.0)


def _animate_typing():
    global typing_dots_state, typing_after_id
    if not typing_label:
        return

    states = [
        ".    ",
        ". .  ",
        ". . .",
        " . . ",
        "  . .",
        ". . .",
    ]
    typing_label.configure(text=states[typing_dots_state % len(states)])
    typing_dots_state += 1
    typing_after_id = root.after(350, _animate_typing)


def hide_typing_indicator():
    global typing_frame, typing_label, typing_after_id
    if typing_after_id:
        root.after_cancel(typing_after_id)
        typing_after_id = None
    if typing_frame:
        typing_frame.destroy()
        typing_frame = None
        typing_label = None


PLACEHOLDER_TEXT = "Message the assistant..."
_has_placeholder = True


def show_placeholder():
    global _has_placeholder
    if not entry.get():
        entry.insert(0, PLACEHOLDER_TEXT)
        entry.configure(fg=PLACEHOLDER)
        _has_placeholder = True


def hide_placeholder(event=None):
    global _has_placeholder
    if _has_placeholder:
        entry.delete(0, tk.END)
        entry.configure(fg=INPUT_FG)
        _has_placeholder = False


def on_focus_out(event=None):
    if not entry.get().strip():
        entry.delete(0, tk.END)
        show_placeholder()


def _on_mousewheel(event):
    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def _on_container_resize(event):
    canvas.itemconfigure(canvas_window_id, width=event.width)


def show_auth_message(message: str, is_error: bool = True):
    auth_message_label.config(
        text=message,
        fg=ERROR_TEXT if is_error else SUCCESS_TEXT,
    )


def clear_auth_message():
    auth_message_label.config(text="")


def switch_auth_view(view: str, message: str = "", is_error: bool = True):
    if view == "register":
        auth_subtitle.config(text="Create a new user ID to keep chats separate.")
        login_form_frame.pack_forget()
        login_button_row.pack_forget()
        register_form_frame.pack(fill="x", padx=32, pady=(24, 10))
        register_button_row.pack(fill="x", padx=32, pady=(0, 12))
        root.after(100, lambda: register_user_entry.focus_set())
    else:
        auth_subtitle.config(text="Sign in with your user ID to access saved chats.")
        register_form_frame.pack_forget()
        register_button_row.pack_forget()
        login_form_frame.pack(fill="x", padx=32, pady=(24, 10))
        login_button_row.pack(fill="x", padx=32, pady=(0, 12))
        root.after(100, lambda: login_user_entry.focus_set())

    if message:
        show_auth_message(message, is_error=is_error)
    else:
        clear_auth_message()


def register_user():
    user_id = register_user_entry.get().strip()
    password = register_password_entry.get().strip()
    confirm_password = register_confirm_entry.get().strip()
    if not user_id or not password:
        show_auth_message("User ID and password are required.")
        return
    if password != confirm_password:
        show_auth_message("Passwords do not match.")
        return

    users = load_users()
    if user_id in users:
        show_auth_message("User ID already exists. Please log in.")
        return

    users[user_id] = {"password_hash": hash_password(password), "created_at": now_iso()}
    save_users(users)
    register_user_entry.delete(0, tk.END)
    register_password_entry.delete(0, tk.END)
    register_confirm_entry.delete(0, tk.END)
    login_user_entry.delete(0, tk.END)
    login_password_entry.delete(0, tk.END)
    login_user_entry.insert(0, user_id)
    switch_auth_view("login", "Registration successful. You can now log in.", is_error=False)


def complete_login(user_id: str):
    global current_user_id, conversations, current_conversation_id
    current_user_id = user_id
    conversations = load_conversations()
    if conversations:
        current_conversation_id = conversations[0]["id"]
    else:
        current_conversation_id = create_conversation()["id"]

    auth_frame.pack_forget()
    app_shell.pack(fill="both", expand=True)
    refresh_sidebar()
    load_conversation(current_conversation_id)
    root.after(100, lambda: entry.focus_set())


def login_user():
    user_id = login_user_entry.get().strip()
    password = login_password_entry.get().strip()
    if not user_id or not password:
        show_auth_message("User ID and password are required.")
        return

    if user_id == ADMIN_USER_ID and password == ADMIN_PASSWORD:
        show_auth_message("Opening admin dashboard...", is_error=False)
        track_login_event(user_id, "admin")
        webbrowser.open(ADMIN_DASHBOARD_URL)
        return

    users = load_users()
    user = users.get(user_id)
    if not user or user.get("password_hash") != hash_password(password):
        show_auth_message("Invalid user ID or password.")
        return

    show_auth_message("")
    track_login_event(user_id, "user")
    complete_login(user_id)


def logout_user():
    global current_user_id, conversations, current_conversation_id
    current_user_id = None
    conversations = []
    current_conversation_id = None
    app_shell.pack_forget()
    login_user_entry.delete(0, tk.END)
    login_password_entry.delete(0, tk.END)
    register_user_entry.delete(0, tk.END)
    register_password_entry.delete(0, tk.END)
    register_confirm_entry.delete(0, tk.END)
    switch_auth_view("login")
    auth_frame.pack(fill="both", expand=True)


root = tk.Tk()
root.title("TerraLaw BD")
root.geometry("1180x860")
root.minsize(980, 680)
root.configure(bg=BG_APP)

try:
    import ctypes
    root.update()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
    )
except Exception:
    pass

auth_frame = Frame(root, bg=BG_APP)

auth_card = Frame(auth_frame, bg=BG_SURFACE, highlightbackground=CARD_SHADOW, highlightthickness=1)
auth_card.place(relx=0.5, rely=0.5, anchor="center", width=440, height=460)

auth_title = tk.Label(
    auth_card,
    text="TerraLaw BD",
    bg=BG_SURFACE,
    fg=TITLE_TEXT,
    font=(FONT_FAMILY, 20, "bold"),
)
auth_title.pack(pady=(28, 8))

auth_subtitle = tk.Label(
    auth_card,
    text="Sign in with your user ID to access saved chats.",
    bg=BG_SURFACE,
    fg=MUTED_TEXT,
    font=(FONT_FAMILY, 10),
)
auth_subtitle.pack()

login_form_frame = Frame(auth_card, bg=BG_SURFACE)
login_form_frame.pack(fill="x", padx=32, pady=(24, 10))

tk.Label(login_form_frame, text="User ID", bg=BG_SURFACE, fg=PRIMARY_TEXT, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")
login_user_entry = tk.Entry(login_form_frame, font=(FONT_FAMILY, 11), bg=INPUT_BG, fg=INPUT_FG, relief="solid", bd=1)
login_user_entry.pack(fill="x", ipady=8, pady=(6, 14))

tk.Label(login_form_frame, text="Password", bg=BG_SURFACE, fg=PRIMARY_TEXT, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")
login_password_entry = tk.Entry(login_form_frame, font=(FONT_FAMILY, 11), bg=INPUT_BG, fg=INPUT_FG, relief="solid", bd=1, show="*")
login_password_entry.pack(fill="x", ipady=8, pady=(6, 8))
login_password_entry.bind("<Return>", lambda e: login_user())

register_form_frame = Frame(auth_card, bg=BG_SURFACE)

tk.Label(register_form_frame, text="User ID", bg=BG_SURFACE, fg=PRIMARY_TEXT, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")
register_user_entry = tk.Entry(register_form_frame, font=(FONT_FAMILY, 11), bg=INPUT_BG, fg=INPUT_FG, relief="solid", bd=1)
register_user_entry.pack(fill="x", ipady=8, pady=(6, 14))

tk.Label(register_form_frame, text="Password", bg=BG_SURFACE, fg=PRIMARY_TEXT, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")
register_password_entry = tk.Entry(register_form_frame, font=(FONT_FAMILY, 11), bg=INPUT_BG, fg=INPUT_FG, relief="solid", bd=1, show="*")
register_password_entry.pack(fill="x", ipady=8, pady=(6, 14))

tk.Label(register_form_frame, text="Confirm Password", bg=BG_SURFACE, fg=PRIMARY_TEXT, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")
register_confirm_entry = tk.Entry(register_form_frame, font=(FONT_FAMILY, 11), bg=INPUT_BG, fg=INPUT_FG, relief="solid", bd=1, show="*")
register_confirm_entry.pack(fill="x", ipady=8, pady=(6, 8))
register_confirm_entry.bind("<Return>", lambda e: register_user())

auth_message_label = tk.Label(
    auth_card,
    text="",
    bg=BG_SURFACE,
    fg=ERROR_TEXT,
    font=(FONT_FAMILY, 9),
)
auth_message_label.pack(pady=(4, 10))

login_button_row = Frame(auth_card, bg=BG_SURFACE)
login_button_row.pack(fill="x", padx=32, pady=(0, 12))

login_btn = tk.Button(
    login_button_row,
    text="Login",
    command=login_user,
    bg=ACCENT,
    fg="#ffffff",
    activebackground=ACCENT_HOVER,
    activeforeground="#ffffff",
    font=(FONT_FAMILY, 11, "bold"),
    relief="flat",
    bd=0,
    cursor="hand2",
    padx=18,
    pady=10,
)
login_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

register_btn = tk.Button(
    login_button_row,
    text="Register",
    command=lambda: switch_auth_view("register"),
    bg=BG_HEADER,
    fg=TITLE_TEXT,
    activebackground=SIDEBAR_ACTIVE,
    activeforeground=TITLE_TEXT,
    font=(FONT_FAMILY, 11, "bold"),
    relief="flat",
    bd=0,
    cursor="hand2",
    padx=18,
    pady=10,
)
register_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

register_button_row = Frame(auth_card, bg=BG_SURFACE)

create_account_btn = tk.Button(
    register_button_row,
    text="Create Account",
    command=register_user,
    bg=ACCENT,
    fg="#ffffff",
    activebackground=ACCENT_HOVER,
    activeforeground="#ffffff",
    font=(FONT_FAMILY, 11, "bold"),
    relief="flat",
    bd=0,
    cursor="hand2",
    padx=18,
    pady=10,
)
create_account_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

back_to_login_btn = tk.Button(
    register_button_row,
    text="Back to Login",
    command=lambda: switch_auth_view("login"),
    bg=BG_HEADER,
    fg=TITLE_TEXT,
    activebackground=SIDEBAR_ACTIVE,
    activeforeground=TITLE_TEXT,
    font=(FONT_FAMILY, 11, "bold"),
    relief="flat",
    bd=0,
    cursor="hand2",
    padx=18,
    pady=10,
)
back_to_login_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

app_shell = Frame(root, bg=BG_APP)

shell_inner = Frame(app_shell, bg=BG_APP)
shell_inner.pack(fill="both", expand=True, padx=24, pady=22)

sidebar = Frame(shell_inner, bg=BG_SIDEBAR, width=250, highlightbackground=CARD_SHADOW, highlightthickness=1)
sidebar.pack(side="left", fill="y", padx=(0, 18))
sidebar.pack_propagate(False)

sidebar_header = Frame(sidebar, bg=BG_SIDEBAR)
sidebar_header.pack(fill="x", padx=14, pady=(14, 8))

brand_label = tk.Label(
    sidebar_header,
    text="TerraLaw BD",
    bg=BG_SIDEBAR,
    fg=TITLE_TEXT,
    font=(FONT_FAMILY, 16, "bold"),
)
brand_label.pack(anchor="w")

user_display = tk.Label(
    sidebar_header,
    text="Not logged in",
    bg=BG_SIDEBAR,
    fg=MUTED_TEXT,
    font=(FONT_FAMILY, 9),
)
user_display.pack(anchor="w", pady=(2, 4))

history_label = tk.Label(
    sidebar_header,
    text="Saved chats",
    bg=BG_SIDEBAR,
    fg=MUTED_TEXT,
    font=(FONT_FAMILY, 9),
)
history_label.pack(anchor="w", pady=(0, 10))

new_chat_btn = tk.Label(
    sidebar,
    text="+  New chat",
    bg=ACCENT,
    fg="#ffffff",
    font=(FONT_FAMILY, 11, "bold"),
    padx=14,
    pady=10,
    cursor="hand2",
)
new_chat_btn.pack(fill="x", padx=14)
new_chat_btn.bind("<Button-1>", lambda e: start_new_chat())
new_chat_btn.bind("<Enter>", lambda e: new_chat_btn.configure(bg=ACCENT_HOVER))
new_chat_btn.bind("<Leave>", lambda e: new_chat_btn.configure(bg=ACCENT))

logout_btn = tk.Label(
    sidebar,
    text="Log out",
    bg=BG_HEADER,
    fg=TITLE_TEXT,
    font=(FONT_FAMILY, 10, "bold"),
    padx=12,
    pady=8,
    cursor="hand2",
)
logout_btn.pack(fill="x", padx=14, pady=(10, 0))
logout_btn.bind("<Button-1>", lambda e: logout_user())

conversation_list = tk.Listbox(
    sidebar,
    bg=BG_SIDEBAR,
    fg=PRIMARY_TEXT,
    selectbackground=SIDEBAR_ACTIVE,
    selectforeground=TITLE_TEXT,
    activestyle="none",
    highlightthickness=0,
    bd=0,
    font=(FONT_FAMILY, 10),
)
conversation_list.pack(fill="both", expand=True, padx=10, pady=(14, 10))
conversation_list.bind("<<ListboxSelect>>", on_conversation_select)

main_panel = Frame(shell_inner, bg=BG_SURFACE, highlightbackground=CARD_SHADOW, highlightthickness=1)
main_panel.pack(side="left", fill="both", expand=True)

header = Frame(main_panel, bg=BG_HEADER, height=86)
header.pack(fill="x", padx=14, pady=(14, 0))
header.pack_propagate(False)

header_inner = Frame(header, bg=BG_HEADER)
header_inner.pack(fill="both", expand=True, padx=18)

brand_icon = tk.Label(
    header_inner,
    text="◔",
    bg=BG_HEADER,
    fg=ACCENT,
    font=("Segoe UI Symbol", 20),
)
brand_icon.pack(side="left")

title_label = tk.Label(
    header_inner,
    text="TerraLaw BD",
    bg=BG_HEADER,
    fg=TITLE_TEXT,
    font=(FONT_FAMILY, 18, "bold"),
)
title_label.pack(side="left", padx=(10, 0))

subtitle_label = tk.Label(
    header_inner,
    text="Bangladesh land-law assistant",
    bg=BG_HEADER,
    fg=MUTED_TEXT,
    font=(FONT_FAMILY, 10),
)
subtitle_label.pack(side="left", padx=(14, 0), pady=(2, 0))

avatar_badge = tk.Label(
    header_inner,
    text=(current_user_id[:1].upper() if current_user_id else "U"),
    bg=BG_SURFACE,
    fg=TITLE_TEXT,
    font=(FONT_FAMILY, 11, "bold"),
    padx=12,
    pady=8,
)
avatar_badge.pack(side="right")

accent_line = Frame(main_panel, bg=ACCENT, height=2)
accent_line.pack(fill="x", padx=14)

container = Frame(main_panel, bg=BG_SURFACE)
container.pack(fill="both", expand=True, padx=14)

canvas = Canvas(container, bg=BG_SURFACE, highlightthickness=0, bd=0)
canvas.pack(fill="both", expand=True)

chat_frame = Frame(canvas, bg=BG_SURFACE)
canvas_window_id = canvas.create_window((0, 0), window=chat_frame, anchor="nw")

chat_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
container.bind("<Configure>", _on_container_resize)
canvas.bind_all("<MouseWheel>", _on_mousewheel)

input_border = Frame(main_panel, bg=BORDER_COLOR, height=1)
input_border.pack(fill="x", padx=14)

input_area = Frame(main_panel, bg=BG_SURFACE, pady=16)
input_area.pack(fill="x", padx=14)

input_inner = Frame(input_area, bg=BG_SURFACE)
input_inner.pack(fill="x", padx=16)

entry_border = Frame(
    input_inner,
    bg=BORDER_COLOR,
    padx=1,
    pady=1,
    highlightbackground=CARD_SHADOW,
    highlightthickness=1,
)
entry_border.pack(side="left", fill="x", expand=True, padx=(0, 10))

entry = tk.Entry(
    entry_border,
    font=(FONT_FAMILY, 12),
    bg=INPUT_BG,
    fg=PLACEHOLDER,
    insertbackground=INPUT_FG,
    relief="flat",
    bd=0,
)
entry.pack(fill="x", ipady=14, padx=14)
entry.bind("<Return>", lambda e: (hide_placeholder(), send_message()))
entry.bind("<FocusIn>", hide_placeholder)
entry.bind("<FocusOut>", on_focus_out)
entry.insert(0, PLACEHOLDER_TEXT)

send_btn = tk.Button(
    input_inner,
    text="Send",
    command=lambda: (hide_placeholder(), send_message()),
    bg=ACCENT,
    fg="#ffffff",
    activebackground=ACCENT_HOVER,
    activeforeground="#ffffff",
    font=(FONT_FAMILY, 14, "bold"),
    relief="flat",
    bd=0,
    padx=20,
    pady=12,
    cursor="hand2",
)
send_btn.pack(side="right")

footer = tk.Label(
    main_panel,
    text="Please double-check responses with official records and legal counsel.",
    bg=BG_SURFACE,
    fg=MUTED_TEXT,
    font=(FONT_FAMILY, 9),
    pady=10,
)
footer.pack(fill="x", padx=14)

auth_frame.pack(fill="both", expand=True)
root.after(100, lambda: login_user_entry.focus_set())

root.mainloop()
