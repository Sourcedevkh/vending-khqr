from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk

from app.config import load_config
from app.models import PaymentResult, Product
from app.payway_service import PaywayService, PaywayServiceError
from app.product_catalog import ProductCatalog
from utils.module import ask_confirmation


class VendingApp:
    MAX_CODE_LENGTH = 2
    QR_EXPIRE_SECONDS = 180
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "123"

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Eroxi Vending Machine")
        self.root.geometry("800x700")
        self.root.configure(bg="#0b1a2b")
        try:
            icon_img = tk.PhotoImage(file="assets/catping.png")
            self.root.iconphoto(False, icon_img)
        except Exception:
            pass # Fallback if file is missing

        project_root = Path(__file__).resolve().parents[1]
        self.products_path = project_root / "products.json"
        self.catalog = ProductCatalog(self.products_path)

        self.config = load_config()
        self.payway_service: PaywayService | None = None
        self._input_code = ""
        self._qr_photo: ImageTk.PhotoImage | None = None
        self._countdown_after_id: str | None = None
        self._seconds_left = self.QR_EXPIRE_SECONDS

        self.code_var = tk.StringVar(value="")

        self.main_container: tk.Frame | None = None
        self.admin_container: tk.Frame | None = None

        self._build_main_ui()
        self._bind_events()
        self._init_payment_service()

    def run(self) -> None:
        self.root.mainloop()

    def _build_main_ui(self) -> None:
        self.main_container = tk.Frame(self.root, bg="#0b1a2b")
        self.main_container.pack(fill="both", expand=True, padx=40, pady=40)

        self.title_label = tk.Label(
            self.main_container,
            text="Eroxi Vending Machine",
            bg="#0b1a2b",
            fg="white",
            font=("Helvetica", 24, "bold"),
            cursor="hand2",
        )
        self.title_label.pack(pady=(10, 5))
        self.title_label.bind("<Button-1>", self._on_title_click)

        tk.Label(
            self.main_container,
            text="Type 2-digit code to purchase",
            bg="#0b1a2b",
            fg="#9bb3c9",
            font=("Helvetica", 12),
        ).pack(pady=(0, 20))

        self.code_entry = tk.Entry(
            self.main_container,
            textvariable=self.code_var,
            justify="center",
            font=("Courier", 24, "bold"),
            width=10,
            bg="#13263a",
            fg="white",
            insertbackground="white",
            relief="flat",
        )
        self.code_entry.pack(ipady=15, pady=(0, 20))
        self.code_entry.focus_set()

        self.timer_label = tk.Label(
            self.main_container,
            text="QR expires in 3:00",
            bg="#0b1a2b",
            fg="#35d07f",
            font=("Helvetica", 12, "bold"),
        )

        self.qr_frame = tk.Frame(self.main_container, bg="#0b1a2b")
        self.qr_frame.pack(pady=10)

        self.qr_label = tk.Label(self.qr_frame, bg="#0b1a2b")
        self.qr_label.pack()

    def _bind_events(self) -> None:
        self.root.bind("<Key>", self._on_key_event)

    def _on_title_click(self, _event: tk.Event) -> None:
        if self._show_login_dialog():
            self._open_admin_form_in_place()

    def _show_login_dialog(self) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Secure Access")
        dialog.geometry("350x260")
        dialog.configure(bg="#ffffff")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Admin Login", bg="white", font=("Helvetica", 14, "bold")).pack(pady=15)
        
        u_frame = tk.Frame(dialog, bg="white")
        u_frame.pack(fill="x", padx=30)
        tk.Label(u_frame, text="Username", bg="white", fg="#666").pack(side="left")
        username_entry = tk.Entry(dialog)
        username_entry.pack(fill="x", padx=30, pady=(0, 10))

        p_frame = tk.Frame(dialog, bg="white")
        p_frame.pack(fill="x", padx=30)
        tk.Label(p_frame, text="Password", bg="white", fg="#666").pack(side="left")
        password_entry = tk.Entry(dialog, show="*")
        password_entry.pack(fill="x", padx=30)

        error_label = tk.Label(dialog, text="", bg="white", fg="#ff4d4f", font=("Helvetica", 9))
        error_label.pack(pady=5)

        state = {"ok": False}

        def do_login() -> None:
            if username_entry.get().strip() == self.ADMIN_USERNAME and password_entry.get() == self.ADMIN_PASSWORD:
                state["ok"] = True
                dialog.destroy()
            else:
                error_label.config(text="Invalid Username or Password")

        btn_f = tk.Frame(dialog, bg="white")
        btn_f.pack(pady=10)
        tk.Button(
            btn_f,
            text="Login",
            width=12,
            bg="#1f6feb",
            fg="black",
            activebackground="#1758c0",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Helvetica", 11, "bold"),
            padx=14,
            pady=6,
            cursor="hand2",
            command=do_login,
        ).pack()

        password_entry.bind("<Return>", lambda _e: do_login())
        username_entry.focus_set()
        self.root.wait_window(dialog)
        return state["ok"]

    def _open_admin_form_in_place(self) -> None:
        if self.main_container:
            self.main_container.pack_forget()

        self.admin_container = tk.Frame(self.root, bg="#f0f2f5")
        self.admin_container.pack(fill="both", expand=True)

        # Dashboard Header
        top_bar = tk.Frame(self.admin_container, bg="#ffffff", height=60)
        top_bar.pack(fill="x")
        tk.Label(
            top_bar, text="Product Inventory", 
            bg="white", fg="#1a1a1a", font=("Helvetica", 18, "bold")
        ).pack(side="left", padx=25, pady=15)

        # Scrollable Area Setup
        canvas_container = tk.Frame(self.admin_container, bg="#f0f2f5")
        canvas_container.pack(fill="both", expand=True, padx=20, pady=(10, 0))

        canvas = tk.Canvas(canvas_container, bg="#f0f2f5", highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview, width=12)
        
        # This frame holds everything (Header + Rows) to ensure perfect alignment
        scroll_host = tk.Frame(canvas, bg="#f0f2f5")
        canvas_window = canvas.create_window((0, 0), window=scroll_host, anchor="nw")

        # Design: Modern Table Header
        header_card = tk.Frame(scroll_host, bg="#13263a", padx=10, pady=12)
        header_card.pack(fill="x", pady=(0, 5))
        
        header_card.grid_columnconfigure(0, weight=1) # ID
        header_card.grid_columnconfigure(1, weight=2) # Price
        header_card.grid_columnconfigure(2, weight=4) # Name
        header_card.grid_columnconfigure(3, weight=0, minsize=110) # Actions

        h_style = {"bg": "#13263a", "fg": "white", "font": ("Helvetica", 10, "bold")}
        
        tk.Label(header_card, text="ID CODE", **h_style).grid(row=0, column=0, sticky="ew", padx=15)
        tk.Label(header_card, text="PRICE (KHR)", **h_style).grid(row=0, column=1, sticky="ew", padx=15)
        tk.Label(header_card, text="PRODUCT NAME", **h_style).grid(row=0, column=2, sticky="ew", padx=15)
        tk.Label(header_card, text="ACTIONS", **h_style).grid(row=0, column=3, sticky="ew", padx=10)

        # Container for the dynamic rows
        rows_host = tk.Frame(scroll_host, bg="#f0f2f5")
        rows_host.pack(fill="x")

        # Scrolling logic
        # --- Scrolling Logic ---
        def update_scroll_region(e): 
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        scroll_host.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Make the canvas take keyboard focus
        canvas.focus_set()

        # Keyboard and Mousewheel navigation
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_key_press(event):
            if event.keysym == 'Up':
                canvas.yview_scroll(-1, "units")
            elif event.keysym == 'Down':
                canvas.yview_scroll(1, "units")

        # Bindings
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<KeyPress-Up>", _on_key_press)
        canvas.bind_all("<KeyPress-Down>", _on_key_press)

        # Global Mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        row_models = []

        def add_row(item: dict) -> None:
            # Row "Card" styling
            row_card = tk.Frame(rows_host, bg="white", highlightthickness=1, highlightbackground="#e1e4e8")
            row_card.pack(fill="x", pady=2)

            row_card.grid_columnconfigure(0, weight=1)
            row_card.grid_columnconfigure(1, weight=2)
            row_card.grid_columnconfigure(2, weight=4)
            row_card.grid_columnconfigure(3, weight=0, minsize=110)

            c_var = tk.StringVar(value=str(item.get("code", "")))
            p_var = tk.StringVar(value=str(item.get("price", "")))
            n_var = tk.StringVar(value=str(item.get("product", "")))

            # Input styling
            e_opts = {"font": ("Helvetica", 11), "relief": "flat", "bg": "#f9fafb"}
            
            tk.Entry(row_card, textvariable=c_var, **e_opts).grid(row=0, column=0, padx=15, pady=12, sticky="ew")
            tk.Entry(row_card, textvariable=p_var, **e_opts).grid(row=0, column=1, padx=15, pady=12, sticky="ew")
            tk.Entry(row_card, textvariable=n_var, **e_opts).grid(row=0, column=2, padx=15, pady=12, sticky="ew")

            def delete_this():
                row_card.destroy()
                row_models[:] = [m for m in row_models if m["frame"] != row_card]

            tk.Button(
                row_card, text="Remove", fg="#ff4d4f", bg="white", 
                relief="flat", font=("Helvetica", 9, "bold"), cursor="hand2",
                activebackground="#fff1f0", command=delete_this
            ).grid(row=0, column=3, padx=10)

            row_models.append({"frame": row_card, "code": c_var, "price": p_var, "name": n_var})

        # Load Existing
        for p in self._load_products_for_admin():
            add_row(p)

        # Footer Actions
        footer = tk.Frame(self.admin_container, bg="white", pady=20, padx=30)
        footer.pack(fill="x")

        tk.Button(
            footer, text="+ Add New Item", bg="#007bff", fg="black", cursor="hand2",
            relief="flat", font=("Helvetica", 10, "bold"), padx=15, pady=8,
            command=lambda: add_row({})
        ).pack(side="left")

        def exit_admin():
            canvas.unbind_all("<MouseWheel>")
            self.admin_container.destroy()
            self.admin_container = None
            self.main_container.pack(fill="both", expand=True, padx=40, pady=40)
            self.code_entry.focus_set()

        leave_button = tk.Label(
            footer,
            text="Leave",
            bg="#d32f2f",
            fg="white",
            padx=15,
            pady=8,
            cursor="hand2",
            font=("Helvetica", 10, "bold"),
        )
        leave_button.pack(side="right", padx=(10, 0))
        leave_button.bind("<Button-1>", lambda _event: exit_admin())
        leave_button.bind("<Enter>", lambda _event: leave_button.config(bg="#b71c1c"))
        leave_button.bind("<Leave>", lambda _event: leave_button.config(bg="#d32f2f"))

        def save_inventory():
            if not ask_confirmation("Confirm Save", "Do you want to save all changes to the catalog?"):
                return
            data = []
            for m in row_models:
                c, p, n = m["code"].get().strip(), m["price"].get().strip(), m["name"].get().strip()
                if not c and not p and not n: continue
                if not (c and p and n and p.isdigit()):
                    messagebox.showwarning("Incomplete", "Please ensure all rows have an ID, Name, and numeric Price.")
                    return
                data.append({"code": c, "price": int(p), "product": n})
            
            data.sort(key=lambda x: int(x["code"]) if x["code"].isdigit() else 999)
            with self.products_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.catalog = ProductCatalog(self.products_path)
            messagebox.showinfo("Saved", "Product updated successfully")

        tk.Button(
            footer, text="Save Changes", bg="#35d07f", fg="black", cursor="hand2",
            relief="flat", font=("Helvetica", 10, "bold"), padx=20, pady=8,
            command=save_inventory
        ).pack(side="right")

    def _load_products_for_admin(self) -> list:
        try:
            with self.products_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: return []

    def _init_payment_service(self) -> None:
        try:
            self.payway_service = PaywayService(self.config)
        except PaywayServiceError as error:
            self.payway_service = None
            self.root.title(f"Eroxi Vending Machine - {error}")

    def _on_key_event(self, event: tk.Event) -> None:
        if self.admin_container: return
        if event.char.isdigit():
            self._append_digit(event.char)
        elif event.keysym == "Return":
            self._confirm_code()
        elif event.keysym == "BackSpace":
            self._backspace()
        elif event.keysym == "Escape":
            self._clear_all()

    def _append_digit(self, digit: str) -> None:
        if len(self._input_code) >= self.MAX_CODE_LENGTH:
            self._input_code = ""
        self._input_code += digit
        self.code_var.set(self._input_code)
        if len(self._input_code) == self.MAX_CODE_LENGTH:
            self._confirm_code(auto_trigger=True)

    def _backspace(self) -> None:
        self._input_code = self._input_code[:-1]
        self.code_var.set(self._input_code)

    def _clear_input(self) -> None:
        self._input_code = ""
        self.code_var.set("")

    def _clear_all(self) -> None:
        self._clear_input()
        if self._countdown_after_id:
            self.root.after_cancel(self._countdown_after_id)
            self._countdown_after_id = None
        if self.timer_label.winfo_ismapped():
            self.timer_label.pack_forget()
        self._qr_photo = None
        self.qr_label.config(image="")
        self.root.title("Eroxi Vending Machine")

    def _confirm_code(self, auto_trigger: bool = False) -> None:
        if not self._input_code or not self.payway_service: return
        product = self.catalog.find_by_code(self._input_code)
        if not product:
            if auto_trigger: self._clear_input()
            return
        try:
            payment = self.payway_service.generate_qr_for_product(product)
            self._apply_payment_result(product, payment)
            self._clear_input()
        except PaywayServiceError as error:
            self.root.title(f"Error: {error}")

    def _apply_payment_result(self, product: Product, payment: PaymentResult) -> None:
        self.root.title(f"Eroxi Vending Machine - {product.name} - {payment.amount_khr:,} KHR")
        if payment.qr_image_data:
            self._render_template_qr(payment.qr_image_data)
            self._start_qr_countdown()

    def _render_template_qr(self, image_data_uri: str) -> None:
        data = image_data_uri.replace("data:image/png;base64,", "")
        image = Image.open(BytesIO(base64.b64decode(data))).convert("RGBA")
        image = image.resize((300, 600), Image.Resampling.LANCZOS)
        self._qr_photo = ImageTk.PhotoImage(image)
        self.qr_label.config(image=self._qr_photo)

    def _start_qr_countdown(self) -> None:
        if self._countdown_after_id: self.root.after_cancel(self._countdown_after_id)
        if not self.timer_label.winfo_ismapped(): self.timer_label.pack(before=self.qr_frame, pady=(0, 10))
        self._seconds_left = self.QR_EXPIRE_SECONDS
        self._tick_countdown()

    def _tick_countdown(self) -> None:
        if self._seconds_left <= 0:
            self.timer_label.config(text="QR expires in 0:00", fg="#ff4d4f")
            return
        self._seconds_left -= 1
        minutes, seconds = divmod(self._seconds_left, 60)
        color = "#35d07f" if self._seconds_left > 60 else "#ff4d4f"
        self.timer_label.config(text=f"QR expires in {minutes}:{seconds:02d}", fg=color)
        self._countdown_after_id = self.root.after(1000, self._tick_countdown)

    @staticmethod
    def _format_khr(amount: int) -> str:
        return f"{amount:,}"
