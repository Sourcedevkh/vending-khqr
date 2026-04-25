import tkinter as tk
from tkinter import messagebox

def ask_confirmation(title: str, message: str) -> bool:
    """
    Displays a standardized Yes/No confirmation dialog.
    Returns True if confirmed, False otherwise.
    """
    return messagebox.askyesno(title=title, message=message)