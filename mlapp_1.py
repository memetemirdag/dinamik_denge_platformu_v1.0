import cv2
import mediapipe as mp
import numpy as np
import time
import os
import sys
# Windows Türkçe konsolunda (cp1254) emoji/unicode karakterlerin çökmesini önle
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass
import subprocess
from datetime import datetime
import matplotlib.pyplot as plt
import csv
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
from scipy.signal import butter, filtfilt


# ==================== KAMERA AYARLARI ====================
# Telefon kamerası için:
# 1) Telefona IP Webcam / DroidCam benzeri uygulama kur.
# 2) Telefon ve bilgisayar aynı Wi-Fi ağında olsun.
# 3) Uygulamada görünen IP adresini PHONE_CAM_URL içine yaz.
#
# Bilgisayar kamerasına dönmek için USE_PHONE_CAMERA = False yapman yeterli.
USE_PHONE_CAMERA = True
PHONE_CAM_URL = "http://localhost:8080/video"  # Burayı telefondaki gerçek IP ile değiştir
PC_CAMERA_INDEX = 0

# Telefon görüntüsü yan/ters gelirse aşağıdaki ayarları değiştir:
# ROTATE_FRAME seçenekleri: None, "CW", "CCW", "180"
ROTATE_FRAME = None
FLIP_FRAME_HORIZONTAL = True

# İstersen işlem yükünü azaltmak için görüntüyü küçültebilirsin.
# None bırakılırsa kamera çözünürlüğü aynen kullanılır. Örnek: (1280, 720) veya (640, 480)
FRAME_RESIZE = None

# ==================== KAMERA KAYIT AYARLARI ====================
# Kamera görüntüsünü video dosyasına kaydeder.
SAVE_CAMERA_RECORDING = True

# False: Program açık olduğu sürece görüntüyü kaydeder.
# True : Sadece SPACE ile RUNNING yapılınca kaydeder.
RECORD_ONLY_WHEN_RUNNING = False

# Çıkış klasörü ve video ayarları
VIDEO_OUTPUT_DIR = "camera_records"
VIDEO_FPS = 30.0
VIDEO_CODEC = "mp4v"   # Alternatif: "XVID" kullanırsan dosya uzantısını .avi yapabilirsin.
VIDEO_EXTENSION = ".mp4"

# ==================== MATLAB GUI KONTROL AYARLARI ====================
# Python girişinden sonra bu MLAPP açılır. MATLAB'daki BAŞLAT/DURDUR butonları
# command.txt dosyasına komut yazar; Python bu komutları okuyarak sistemi kontrol eder.
import json
CONTROL_DIR = os.path.abspath("matlab_control")
COMMAND_FILE = os.path.join(CONTROL_DIR, "command.txt")
PYTHON_STATUS_FILE = os.path.join(CONTROL_DIR, "python_status.txt")
MATLAB_LAUNCHER_FUNCTION = "run_kullanici_arayuz_pose"
MATLAB_APP_FILE = os.path.abspath("kullanici_arayuz_kontrollu.mlapp")
MATLAB_EXE = "matlab"  # MATLAB PATH'te değilse tam yolu yaz: r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe"



# ==================== GÖRSEL ÇİZİM AYARLARI ====================
# False: MediaPipe'in tüm gövde/iskelet çizgileri kapalı olur.
# Bu sürümde sadece önde algılanan bacağın kalça-diz-ayak bileği çizgileri gösterilir.
DRAW_FULL_BODY_LANDMARKS = False
DRAW_TRUNK_LINE = False
DRAW_ACTIVE_LEG_LINES = True
DRAW_JOINT_POINTS = True
DRAW_ANGLE_ARCS = True

# Aktif/öndeki bacak seçimi MediaPipe z derinlik değerine göre yapılır.
# MediaPipe'ta z değeri daha küçük/negatif olan taraf kameraya daha yakındır.
FRONT_LEG_Z_MARGIN = 0.015

# ==================== GİRİŞ EKRANI (Tkinter) ====================

# Kullanıcı veritabanı: {kullanici_adi: {"password": ..., "role": "admin"/"user", "height": ..., "weight": ...}}
USER_DB = {
    "admin": {"password": "1234", "role": "admin", "height": 175, "weight": 75}
}

class LoginWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Dinamik Denge Platformu — Giriş")
        self.root.geometry("1920x1080")
        self.root.configure(bg="#07111d")
        self.root.resizable(False, False)

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 420) // 2
        y = (sh - 520) // 2
        self.root.geometry(f"420x520+{x}+{y}")

        self.logged_in    = False
        self.username     = ""
        self.current_role = ""
        self.height_cm    = tk.IntVar(value=170)
        self.weight_kg    = tk.IntVar(value=70)

        self._build_login()
        self.root.mainloop()

    # ── YARDIMCI STİL ──────────────────────────────────────────
    def _entry_style(self, parent, placeholder=""):
        e = tk.Entry(parent,
                     bg="#112233", fg="#e8f4ff",
                     insertbackground="#e8f4ff",
                     relief="flat", bd=0,
                     font=("Courier New", 12),
                     highlightthickness=1,
                     highlightbackground="#1a3a5c",
                     highlightcolor="#3a8fd4")
        e.insert(0, placeholder)
        e.config(fg="#3a5a7a")
        def on_focus_in(ev):
            if e.get() == placeholder:
                e.delete(0, tk.END)
                e.config(fg="#e8f4ff")
        def on_focus_out(ev):
            if e.get() == "":
                e.insert(0, placeholder)
                e.config(fg="#3a5a7a")
        e.bind("<FocusIn>",  on_focus_in)
        e.bind("<FocusOut>", on_focus_out)
        return e

    def _label(self, parent, text, size=11, color="#7fa8c9", bold=False):
        w = tk.Label(parent, text=text,
                     bg="#07111d", fg=color,
                     font=("Courier New", size, "bold" if bold else "normal"))
        return w

    # ── GİRİŞ EKRANI ───────────────────────────────────────────
    def _build_login(self):
        for w in self.root.winfo_children():
            w.destroy()

        card = tk.Frame(self.root, bg="#0d1f30",
                        highlightthickness=1,
                        highlightbackground="#1a3a5c")
        card.place(relx=0.5, rely=0.5, anchor="center",
                   width=360, height=440)

        # Logo
        tk.Label(card, text="⚡", bg="#0d1f30", fg="#00c9a7",
                 font=("Courier New", 32)).pack(pady=(30, 4))

        tk.Label(card, text="DİNAMİK DENGE PLATFORMU",
                 bg="#0d1f30", fg="#e8f4ff",
                 font=("Courier New", 11, "bold")).pack()

        tk.Label(card, text="HAREKET ANALİZ SİSTEMİ v2",
                 bg="#0d1f30", fg="#3a5a7a",
                 font=("Courier New", 8)).pack(pady=(2, 20))

        # ── Kullanıcı Adı
        tk.Label(card, text="KULLANICI ADI",
                 bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 9)).pack(anchor="w", padx=30)

        self.user_entry = self._entry_style(card, "kullanici.adi")
        self.user_entry.pack(fill="x", padx=30, pady=(4, 12), ipady=7)

        # ── Şifre
        tk.Label(card, text="ŞİFRE",
                 bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 9)).pack(anchor="w", padx=30)

        self.pass_entry = tk.Entry(card,
                                   bg="#112233", fg="#e8f4ff",
                                   insertbackground="#e8f4ff",
                                   relief="flat", bd=0,
                                   font=("Courier New", 12),
                                   highlightthickness=1,
                                   highlightbackground="#1a3a5c",
                                   highlightcolor="#3a8fd4",
                                   show="●")
        self.pass_entry.pack(fill="x", padx=30, pady=(4, 16), ipady=7)

        # ── Hata mesajı
        self.error_var = tk.StringVar()
        tk.Label(card, textvariable=self.error_var,
                 bg="#0d1f30", fg="#e05e5e",
                 font=("Courier New", 9)).pack()

        # ── Giriş Butonu
        btn = tk.Button(card, text="GİRİŞ YAP →",
                        bg="#0f4c81", fg="white",
                        activebackground="#1a6bb5",
                        activeforeground="white",
                        relief="flat", bd=0,
                        font=("Courier New", 11, "bold"),
                        cursor="hand2",
                        command=self._do_login)
        btn.pack(fill="x", padx=30, pady=(10, 0), ipady=10)

        self.pass_entry.bind("<Return>", lambda e: self._do_login())
        self.user_entry.bind("<Return>", lambda e: self._do_login())

        tk.Label(card, text="─" * 44,
                 bg="#0d1f30", fg="#1a3a5c",
                 font=("Courier New", 8)).pack(pady=(18, 4))

        tk.Label(card, text="🔒  Güvenli bağlantı · Butterworth+3D",
                 bg="#0d1f30", fg="#2a4a6a",
                 font=("Courier New", 8)).pack()

    def _do_login(self):
        u = self.user_entry.get().strip()
        p = self.pass_entry.get()
        if u in ("kullanici.adi", "") or p == "":
            self.error_var.set("Kullanıcı adı ve şifre gereklidir.")
            return
        user_data = USER_DB.get(u)
        if user_data and user_data["password"] == p:
            self.error_var.set("")
            self.logged_in    = True
            self.username     = u
            self.current_role = user_data["role"]
            self.height_cm.set(user_data.get("height", 170))
            self.weight_kg.set(user_data.get("weight", 70))
            self.root.destroy()
        else:
            self.error_var.set("Kullanıcı adı veya şifre hatalı!")

    # ── KONTROL PANELİ ─────────────────────────────────────────
    def _build_dashboard(self):
        self.root.geometry("560x680")
        self.root.title("Dinamik Denge Platformu — Kontrol Paneli")
        for w in self.root.winfo_children():
            w.destroy()

        # ── Topbar
        topbar = tk.Frame(self.root, bg="#0d1f30",
                          highlightthickness=1,
                          highlightbackground="#1a3a5c",
                          height=48)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⚡ Dinamik Denge Platformu",
                 bg="#0d1f30", fg="#e8f4ff",
                 font=("Courier New", 11, "bold")).pack(side="left", padx=16)

        tk.Button(topbar, text="Çıkış",
                  bg="#112233", fg="#7fa8c9",
                  activebackground="#1a3a5c",
                  relief="flat", bd=0,
                  font=("Courier New", 9),
                  cursor="hand2",
                  command=self._do_logout).pack(side="right", padx=12, pady=10, ipadx=10)

        role_color = "#00c9a7" if self.current_role == "admin" else "#3a8fd4"
        role_text  = "ADMİN" if self.current_role == "admin" else "KULLANICI"
        tk.Label(topbar, text=f"[{role_text}]",
                 bg="#0d1f30", fg=role_color,
                 font=("Courier New", 8, "bold")).pack(side="right", padx=2)

        tk.Label(topbar, text=f"👤 {self.username}",
                 bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 9)).pack(side="right", padx=4)

        # ── Ana içerik
        body = tk.Frame(self.root, bg="#07111d")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Başlat Kartı
        start_card = tk.Frame(body, bg="#0d1f30",
                              highlightthickness=1,
                              highlightbackground="#1a3a5c")
        start_card.pack(fill="x", pady=(0, 12))

        tk.Label(start_card, text="🎯  ANALİZ SİSTEMİ",
                 bg="#0d1f30", fg="#e8f4ff",
                 font=("Courier New", 11, "bold")).pack(pady=(16, 2))

        tk.Label(start_card,
                 text="Kamera akışını başlatmak ve eklem açısı ölçümüne\ngeçmek için aşağıdaki butona tıklayın.",
                 bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 9),
                 justify="center").pack(pady=(0, 10))

        self.system_running = False
        self.start_btn = tk.Button(start_card,
                                   text="▶  SİSTEMİ BAŞLAT",
                                   bg="#0a5c4a", fg="white",
                                   activebackground="#00c9a7",
                                   relief="flat", bd=0,
                                   font=("Courier New", 12, "bold"),
                                   cursor="hand2",
                                   command=self._toggle_system)
        self.start_btn.pack(pady=(0, 16), ipadx=24, ipady=10)

        # Durum göstergeleri
        status_row = tk.Frame(start_card, bg="#0d1f30")
        status_row.pack(pady=(0, 14))

        self.dot_labels = {}
        for name, color in [("Kamera", "#00c9a7"), ("Pose Motoru", "#f5a623"), ("Kayıt", "#e05e5e")]:
            f = tk.Frame(status_row, bg="#0d1f30")
            f.pack(side="left", padx=14)
            dot = tk.Label(f, text="●", fg=color, bg="#0d1f30",
                           font=("Courier New", 10))
            dot.pack()
            tk.Label(f, text=name, fg="#3a5a7a", bg="#0d1f30",
                     font=("Courier New", 7)).pack()
            self.dot_labels[name] = dot

        # ── Profil Ayarları Kartı
        prof_card = tk.Frame(body, bg="#0d1f30",
                             highlightthickness=1,
                             highlightbackground="#1a3a5c")
        prof_card.pack(fill="x", pady=(0, 12))

        tk.Label(prof_card, text="⚙  KULLANICI PROFİLİ & ÖLÇÜMLERİ",
                 bg="#0d1f30", fg="#3a8fd4",
                 font=("Courier New", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 8))

        grid = tk.Frame(prof_card, bg="#0d1f30")
        grid.pack(fill="x", padx=16, pady=(0, 8))
        grid.columnconfigure((0, 1), weight=1)

        # Boy
        tk.Label(grid, text="BOY", bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 8)).grid(row=0, column=0, sticky="w", pady=(4,0))
        height_row = tk.Frame(grid, bg="#0d1f30")
        height_row.grid(row=1, column=0, sticky="ew", padx=(0,10))
        self.height_scale = tk.Scale(height_row,
                                     from_=140, to=220,
                                     orient="horizontal",
                                     variable=self.height_cm,
                                     bg="#0d1f30", fg="#3a8fd4",
                                     troughcolor="#112233",
                                     highlightthickness=0,
                                     sliderrelief="flat",
                                     command=lambda _: self._calc_bmi())
        self.height_scale.pack(side="left", fill="x", expand=True)
        self.height_lbl = tk.Label(height_row, text="170 cm",
                                   bg="#0d1f30", fg="#3a8fd4",
                                   font=("Courier New", 10, "bold"), width=7)
        self.height_lbl.pack(side="right")

        # Kilo
        tk.Label(grid, text="KİLO", bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 8)).grid(row=0, column=1, sticky="w", pady=(4,0))
        weight_row = tk.Frame(grid, bg="#0d1f30")
        weight_row.grid(row=1, column=1, sticky="ew")
        self.weight_scale = tk.Scale(weight_row,
                                     from_=30, to=180,
                                     orient="horizontal",
                                     variable=self.weight_kg,
                                     bg="#0d1f30", fg="#3a8fd4",
                                     troughcolor="#112233",
                                     highlightthickness=0,
                                     sliderrelief="flat",
                                     command=lambda _: self._calc_bmi())
        self.weight_scale.pack(side="left", fill="x", expand=True)
        self.weight_lbl = tk.Label(weight_row, text="70 kg",
                                   bg="#0d1f30", fg="#3a8fd4",
                                   font=("Courier New", 10, "bold"), width=7)
        self.weight_lbl.pack(side="right")

        # Cinsiyet & Aktivite
        tk.Label(grid, text="CİNSİYET", bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 8)).grid(row=2, column=0, sticky="w", pady=(10,0))
        self.gender_var = tk.StringVar(value="Erkek")
        gender_menu = ttk.Combobox(grid, textvariable=self.gender_var,
                                   values=["Erkek", "Kadın", "Belirtmek istemiyorum"],
                                   state="readonly", width=20)
        gender_menu.grid(row=3, column=0, sticky="ew", padx=(0,10))

        tk.Label(grid, text="AKTİVİTE SEVİYESİ", bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 8)).grid(row=2, column=1, sticky="w", pady=(10,0))
        self.activity_var = tk.StringVar(value="Orta aktif")
        activity_menu = ttk.Combobox(grid, textvariable=self.activity_var,
                                     values=["Sedanter", "Az aktif", "Orta aktif", "Çok aktif", "Sporcu"],
                                     state="readonly", width=20)
        activity_menu.grid(row=3, column=1, sticky="ew")

        # BMI
        bmi_row = tk.Frame(prof_card, bg="#112233",
                           highlightthickness=1,
                           highlightbackground="#1a3a5c")
        bmi_row.pack(fill="x", padx=16, pady=(6, 4))

        tk.Label(bmi_row, text="VKİ (BMI):",
                 bg="#112233", fg="#7fa8c9",
                 font=("Courier New", 9)).pack(side="left", padx=10, pady=8)

        self.bmi_val_lbl = tk.Label(bmi_row, text="24.2",
                                    bg="#112233", fg="#00c9a7",
                                    font=("Courier New", 16, "bold"))
        self.bmi_val_lbl.pack(side="left", padx=4)

        self.bmi_cat_lbl = tk.Label(bmi_row, text="Normal",
                                    bg="#112233", fg="#00c9a7",
                                    font=("Courier New", 9))
        self.bmi_cat_lbl.pack(side="left")

        # Kaydet
        save_row = tk.Frame(prof_card, bg="#0d1f30")
        save_row.pack(fill="x", padx=16, pady=(4, 14))

        tk.Button(save_row, text="💾  Profili Kaydet",
                  bg="#112233", fg="#3a8fd4",
                  activebackground="#1a3a5c",
                  relief="flat", bd=0,
                  font=("Courier New", 9, "bold"),
                  cursor="hand2",
                  command=self._save_profile).pack(side="left", ipadx=12, ipady=6)

        self.save_ok_lbl = tk.Label(save_row, text="",
                                    bg="#0d1f30", fg="#00c9a7",
                                    font=("Courier New", 9))
        self.save_ok_lbl.pack(side="left", padx=10)

        self._calc_bmi()

        # ── Kullanıcı Yönetimi Butonu (sadece admin)
        if self.current_role == "admin":
            mgmt_row = tk.Frame(body, bg="#07111d")
            mgmt_row.pack(fill="x", pady=(0, 4))
            tk.Button(mgmt_row, text="👥  Kullanıcı Yönetimi",
                      bg="#1a2a3a", fg="#3a8fd4",
                      activebackground="#1a3a5c",
                      relief="flat", bd=0,
                      font=("Courier New", 9, "bold"),
                      cursor="hand2",
                      command=self._open_user_management).pack(side="left", ipadx=14, ipady=7)

    # ── YARDIMCI METHODLAR ─────────────────────────────────────
    def _toggle_system(self):
        self.system_running = not self.system_running
        if self.system_running:
            self.start_btn.config(text="⏸  SİSTEMİ DURDUR", bg="#7b1a1a")
            self.dot_labels["Kamera"].config(fg="#00c9a7")
            self.dot_labels["Pose Motoru"].config(fg="#00c9a7")
            self.dot_labels["Kayıt"].config(fg="#00c9a7")
            self.root.destroy()          # GUI kapat, kamera döngüsüne geç
        else:
            self.start_btn.config(text="▶  SİSTEMİ BAŞLAT", bg="#0a5c4a")
            self.dot_labels["Kamera"].config(fg="#00c9a7")
            self.dot_labels["Pose Motoru"].config(fg="#f5a623")
            self.dot_labels["Kayıt"].config(fg="#e05e5e")

    def _calc_bmi(self):
        h = self.height_cm.get() / 100
        w = self.weight_kg.get()
        bmi = w / (h * h)
        self.height_lbl.config(text=f"{self.height_cm.get()} cm")
        self.weight_lbl.config(text=f"{self.weight_kg.get()} kg")
        self.bmi_val_lbl.config(text=f"{bmi:.1f}")
        if bmi < 18.5:
            cat, color = "Zayıf", "#f5a623"
        elif bmi < 25:
            cat, color = "Normal", "#00c9a7"
        elif bmi < 30:
            cat, color = "Fazla Kilolu", "#f5a623"
        else:
            cat, color = "Obez", "#e05e5e"
        self.bmi_cat_lbl.config(text=cat, fg=color)
        self.bmi_val_lbl.config(fg=color)

    def _save_profile(self):
        # Profil bilgilerini USER_DB'ye kaydet
        if self.username in USER_DB:
            USER_DB[self.username]["height"] = self.height_cm.get()
            USER_DB[self.username]["weight"] = self.weight_kg.get()
        self.save_ok_lbl.config(text="✔ Profil kaydedildi")
        self.root.after(2500, lambda: self.save_ok_lbl.config(text=""))

    def _do_logout(self):
        self.logged_in    = False
        self.username     = ""
        self.current_role = ""
        self.root.geometry("420x520")
        self._build_login()

    # ── KULLANICI YÖNETİMİ EKRANI ──────────────────────────────
    def _open_user_management(self):
        win = tk.Toplevel(self.root)
        win.title("Kullanıcı Yönetimi")
        win.geometry("640x520")
        win.configure(bg="#07111d")
        win.resizable(False, False)
        win.grab_set()

        # ── Başlık
        hdr = tk.Frame(win, bg="#0d1f30", height=48,
                        highlightthickness=1, highlightbackground="#1a3a5c")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="👥  KULLANICI YÖNETİMİ",
                 bg="#0d1f30", fg="#e8f4ff",
                 font=("Courier New", 11, "bold")).pack(side="left", padx=16)
        tk.Label(hdr, text=f"Toplam: {len(USER_DB)} kullanıcı",
                 bg="#0d1f30", fg="#3a5a7a",
                 font=("Courier New", 9)).pack(side="right", padx=16)

        body = tk.Frame(win, bg="#07111d")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # ── Sol: Kullanıcı Listesi
        left = tk.Frame(body, bg="#07111d")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(left, text="KULLANICILAR", bg="#07111d", fg="#7fa8c9",
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 6))

        list_frame = tk.Frame(left, bg="#0d1f30",
                               highlightthickness=1, highlightbackground="#1a3a5c")
        list_frame.pack(fill="both", expand=True)

        self._user_listbox = tk.Listbox(list_frame,
                                         bg="#0d1f30", fg="#e8f4ff",
                                         selectbackground="#1a6bb5",
                                         selectforeground="white",
                                         font=("Courier New", 10),
                                         relief="flat", bd=0,
                                         highlightthickness=0,
                                         activestyle="none")
        self._user_listbox.pack(fill="both", expand=True, padx=2, pady=2)
        self._user_listbox.bind("<<ListboxSelect>>", lambda e: self._load_user_to_form(win))

        self._refresh_user_list()

        # ── Sağ: Form
        right = tk.Frame(body, bg="#07111d", width=260)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        form_card = tk.Frame(right, bg="#0d1f30",
                              highlightthickness=1, highlightbackground="#1a3a5c")
        form_card.pack(fill="both", expand=True)

        tk.Label(form_card, text="KULLANICI DETAYI",
                 bg="#0d1f30", fg="#3a8fd4",
                 font=("Courier New", 9, "bold")).pack(anchor="w", padx=12, pady=(12, 8))

        fields = [
            ("Kullanıcı Adı", "form_uname"),
            ("Şifre",         "form_pass"),
            ("Boy (cm)",      "form_height"),
            ("Kilo (kg)",     "form_weight"),
        ]

        self._form_vars = {}
        for lbl, key in fields:
            tk.Label(form_card, text=lbl.upper(),
                     bg="#0d1f30", fg="#7fa8c9",
                     font=("Courier New", 7)).pack(anchor="w", padx=12, pady=(4, 0))
            var = tk.StringVar()
            show = "●" if key == "form_pass" else ""
            ent = tk.Entry(form_card, textvariable=var,
                           bg="#112233", fg="#e8f4ff",
                           insertbackground="#e8f4ff",
                           relief="flat", bd=0,
                           font=("Courier New", 10),
                           highlightthickness=1,
                           highlightbackground="#1a3a5c",
                           highlightcolor="#3a8fd4",
                           show=show)
            ent.pack(fill="x", padx=12, pady=(2, 0), ipady=5)
            self._form_vars[key] = var

        # Rol seçimi
        tk.Label(form_card, text="ROL",
                 bg="#0d1f30", fg="#7fa8c9",
                 font=("Courier New", 7)).pack(anchor="w", padx=12, pady=(8, 0))
        self._role_var = tk.StringVar(value="user")
        role_frame = tk.Frame(form_card, bg="#0d1f30")
        role_frame.pack(fill="x", padx=12, pady=(2, 0))
        tk.Radiobutton(role_frame, text="Admin", variable=self._role_var, value="admin",
                       bg="#0d1f30", fg="#e8f4ff", selectcolor="#112233",
                       activebackground="#0d1f30", font=("Courier New", 9)).pack(side="left")
        tk.Radiobutton(role_frame, text="Kullanıcı", variable=self._role_var, value="user",
                       bg="#0d1f30", fg="#e8f4ff", selectcolor="#112233",
                       activebackground="#0d1f30", font=("Courier New", 9)).pack(side="left", padx=8)

        # Form mesaj
        self._form_msg = tk.StringVar()
        tk.Label(form_card, textvariable=self._form_msg,
                 bg="#0d1f30", fg="#00c9a7",
                 font=("Courier New", 8),
                 wraplength=220).pack(padx=12, pady=(6, 0))

        # Butonlar
        btn_frame = tk.Frame(form_card, bg="#0d1f30")
        btn_frame.pack(fill="x", padx=12, pady=10)

        tk.Button(btn_frame, text="➕ Ekle / Güncelle",
                  bg="#0a5c4a", fg="white",
                  activebackground="#00c9a7",
                  relief="flat", bd=0,
                  font=("Courier New", 8, "bold"),
                  cursor="hand2",
                  command=lambda: self._save_user(win)).pack(fill="x", ipady=7, pady=(0, 4))

        tk.Button(btn_frame, text="🗑  Kullanıcıyı Sil",
                  bg="#4a1a1a", fg="#e05e5e",
                  activebackground="#7b1a1a",
                  relief="flat", bd=0,
                  font=("Courier New", 8, "bold"),
                  cursor="hand2",
                  command=lambda: self._delete_user(win)).pack(fill="x", ipady=7, pady=(0, 4))

        tk.Button(btn_frame, text="✖  Formu Temizle",
                  bg="#1a2a3a", fg="#7fa8c9",
                  relief="flat", bd=0,
                  font=("Courier New", 8),
                  cursor="hand2",
                  command=self._clear_form).pack(fill="x", ipady=5)

    def _refresh_user_list(self):
        self._user_listbox.delete(0, tk.END)
        for uname, data in USER_DB.items():
            role_tag = "★" if data["role"] == "admin" else "·"
            self._user_listbox.insert(tk.END, f" {role_tag}  {uname}")

    def _load_user_to_form(self, win):
        sel = self._user_listbox.curselection()
        if not sel:
            return
        raw   = self._user_listbox.get(sel[0]).strip()
        uname = raw.split()[-1]
        if uname not in USER_DB:
            return
        data = USER_DB[uname]
        self._form_vars["form_uname"].set(uname)
        self._form_vars["form_pass"].set(data["password"])
        self._form_vars["form_height"].set(str(data.get("height", 170)))
        self._form_vars["form_weight"].set(str(data.get("weight", 70)))
        self._role_var.set(data["role"])
        self._form_msg.set("")

    def _save_user(self, win):
        uname  = self._form_vars["form_uname"].get().strip()
        passwd = self._form_vars["form_pass"].get().strip()
        role   = self._role_var.get()
        try:
            height = int(self._form_vars["form_height"].get())
            weight = int(self._form_vars["form_weight"].get())
        except ValueError:
            self._form_msg.set("❌ Boy/Kilo sayı olmalıdır!")
            return

        if not uname or not passwd:
            self._form_msg.set("❌ Kullanıcı adı ve şifre zorunludur!")
            return
        if len(passwd) < 4:
            self._form_msg.set("❌ Şifre en az 4 karakter olmalı!")
            return

        is_new = uname not in USER_DB
        USER_DB[uname] = {"password": passwd, "role": role,
                           "height": height, "weight": weight}
        self._refresh_user_list()
        msg = f"✔ '{uname}' eklendi." if is_new else f"✔ '{uname}' güncellendi."
        self._form_msg.set(msg)
        win.after(2500, lambda: self._form_msg.set(""))

    def _delete_user(self, win):
        uname = self._form_vars["form_uname"].get().strip()
        if not uname:
            self._form_msg.set("❌ Önce bir kullanıcı seçin.")
            return
        if uname == self.username:
            self._form_msg.set("❌ Kendinizi silemezsiniz!")
            return
        if uname not in USER_DB:
            self._form_msg.set("❌ Kullanıcı bulunamadı.")
            return
        del USER_DB[uname]
        self._refresh_user_list()
        self._clear_form()
        self._form_msg.set(f"✔ '{uname}' silindi.")
        win.after(2500, lambda: self._form_msg.set(""))

    def _clear_form(self):
        for var in self._form_vars.values():
            var.set("")
        self._role_var.set("user")
        self._form_msg.set("")


# ==================== MATLAB GUI KONTROL FONKSİYONLARI ====================
def write_status(text):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    with open(PYTHON_STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(str(text) + "\n")

def clear_command():
    try:
        if os.path.exists(COMMAND_FILE):
            os.remove(COMMAND_FILE)
    except OSError:
        pass

def read_command():
    if not os.path.exists(COMMAND_FILE):
        return None
    try:
        with open(COMMAND_FILE, "r", encoding="utf-8") as f:
            cmd = f.read().strip()
        clear_command()
        return cmd
    except OSError:
        return None

def launch_matlab_gui():
    os.makedirs(CONTROL_DIR, exist_ok=True)
    clear_command()
    write_status("PYTHON_WAITING_FOR_MATLAB_START")

    # Kullanıcı profil bilgilerini MATLAB okuması için JSON dosyasına yaz
    profile_path = os.path.join(CONTROL_DIR, "user_profile.json")
    try:
        profile_data = {
            "username": login.username,
            "height": user_height,
            "weight": user_weight
        }
        with open(profile_path, "w", encoding="utf-8") as pf:
            json.dump(profile_data, pf)
    except Exception as pe:
        print(f"⚠️ Kullanıcı profil dosyası oluşturulamadı: {pe}")

    app_folder = os.getcwd()
    app_folder_matlab = app_folder.replace("\\", "/")
    control_dir_matlab = CONTROL_DIR.replace("\\", "/")

    matlab_cmd = (
        "try, "
        f"addpath('{app_folder_matlab}'); "
        f"{MATLAB_LAUNCHER_FUNCTION}('{control_dir_matlab}'); "
        "catch ME, disp(getReport(ME)); end"
    )

    try:
        subprocess.Popen([MATLAB_EXE, "-nosplash", "-r", matlab_cmd], cwd=os.getcwd())
        print("✅ MATLAB GUI açılmaya çalışılıyor...")
    except Exception as e:
        print("⚠️ MATLAB otomatik açılamadı.")
        print("Sebep:", e)
        print("MATLAB Command Window içine şu komutu elle yazabilirsin:")
        print(f"addpath('{app_folder_matlab}'); {MATLAB_LAUNCHER_FUNCTION}('{control_dir_matlab}')")



def wait_for_matlab_start_command():
    print("MATLAB GUI'den BAŞLAT komutu bekleniyor...")
    print("Çıkmak için bu pencereye gelip Ctrl+C yapabilirsin.")
    write_status("WAITING_START_BUTTON")
    while True:
        cmd = read_command()
        if cmd:
            cmd_upper = cmd.upper()
            if cmd_upper.startswith("START"):
                write_status("START_RECEIVED")
                print(f"▶ MATLAB GUI komutu alındı: {cmd}")
                return cmd
            elif cmd_upper.startswith("STOP"):
                write_status("STOP_BEFORE_START")
                print("MATLAB GUI'den STOP geldi. Çıkılıyor.")
                sys.exit(0)
        time.sleep(0.2)

# ==================== UYGULAMA GİRİŞ NOKTASI ====================
login = LoginWindow()

if not login.logged_in:
    print("Giriş yapılmadı. Çıkılıyor.")
    exit()

user_height = login.height_cm.get()
user_weight = login.weight_kg.get()
print(f"✅ Giriş yapıldı: {login.username} [{login.current_role}]")
print(f"   Boy: {user_height} cm | Kilo: {user_weight} kg")

launch_matlab_gui()



start_command = wait_for_matlab_start_command()

# ==================== MediaPipe ====================
mp_pose = mp.solutions.pose
mp_draw = mp.solutions.drawing_utils

pose = mp_pose.Pose(
    model_complexity=1,
    smooth_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# ==================== Sabitler =====================
VISIBILITY_THRESHOLD = 0.5
SAMPLE_INTERVAL      = 0.033       # ~30 Hz
BUFFER_SIZE          = 90
BUTTERWORTH_ORDER    = 4
BUTTERWORTH_CUTOFF   = 6.0         # Hz
FS                   = 30.0

vertical_ref = np.array([0, -1], dtype=float)

# ==================== Butterworth Filtresi =========
def butter_lowpass(cutoff, fs, order=4):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a

def apply_butter(data, cutoff=BUTTERWORTH_CUTOFF, fs=FS, order=BUTTERWORTH_ORDER):
    if len(data) < BUFFER_SIZE:
        alpha = 0.2
        filtered = [data[0]]
        for v in data[1:]:
            filtered.append(alpha * v + (1 - alpha) * filtered[-1])
        return filtered[-1]
    b, a = butter_lowpass(cutoff, fs, order)
    filtered = filtfilt(b, a, data)
    return filtered[-1]

# ==================== Açı Hesaplama (3D) ===========
def angle_between_3d(v1, v2):
    v1 = np.array(v1, dtype=float)
    v2 = np.array(v2, dtype=float)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cosang = np.dot(v1, v2) / (n1 * n2)
    return np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))

def draw_arc(img, center, v1, v2, radius=35, color=(255, 0, 0)):
    a1 = np.degrees(np.arctan2(v1[1], v1[0]))
    a2 = np.degrees(np.arctan2(v2[1], v2[0]))
    start = int(min(a1, a2))
    end   = int(max(a1, a2))
    cv2.ellipse(img, center, (radius, radius), 0, start, end, color, 2)

# ==================== Visibility Kontrolü ==========
def check_visibility(lm, indices):
    return all(lm[i].visibility >= VISIBILITY_THRESHOLD for i in indices)

def mean_visibility(lm, indices):
    return sum(lm[i].visibility for i in indices) / len(indices)

def select_front_leg(lm):
    """
    Kameraya daha yakın olan bacağı seçer.
    MediaPipe Pose landmarklarında z değeri daha küçük/negatif olan nokta kameraya daha yakındır.
    Kararsız durumda görünürlüğü daha yüksek olan tarafı seçer.
    """
    right_leg = [
        mp_pose.PoseLandmark.RIGHT_HIP,
        mp_pose.PoseLandmark.RIGHT_KNEE,
        mp_pose.PoseLandmark.RIGHT_ANKLE
    ]
    left_leg = [
        mp_pose.PoseLandmark.LEFT_HIP,
        mp_pose.PoseLandmark.LEFT_KNEE,
        mp_pose.PoseLandmark.LEFT_ANKLE
    ]

    right_depth = sum(lm[i].z for i in right_leg) / len(right_leg)
    left_depth = sum(lm[i].z for i in left_leg) / len(left_leg)
    right_vis = mean_visibility(lm, right_leg)
    left_vis = mean_visibility(lm, left_leg)

    # Bir taraf belirgin biçimde daha görünürse önce onu tercih et.
    if right_vis < VISIBILITY_THRESHOLD and left_vis >= VISIBILITY_THRESHOLD:
        chosen = "LEFT"
    elif left_vis < VISIBILITY_THRESHOLD and right_vis >= VISIBILITY_THRESHOLD:
        chosen = "RIGHT"
    else:
        # z farkı belirginse kameraya yakın olan tarafı seç.
        if right_depth < left_depth - FRONT_LEG_Z_MARGIN:
            chosen = "RIGHT"
        elif left_depth < right_depth - FRONT_LEG_Z_MARGIN:
            chosen = "LEFT"
        else:
            # Derinlik farkı çok küçükse daha görünür olan tarafı seç.
            chosen = "RIGHT" if right_vis >= left_vis else "LEFT"

    if chosen == "RIGHT":
        return {
            "side": "RIGHT",
            "S": mp_pose.PoseLandmark.RIGHT_SHOULDER,
            "H": mp_pose.PoseLandmark.RIGHT_HIP,
            "K": mp_pose.PoseLandmark.RIGHT_KNEE,
            "A": mp_pose.PoseLandmark.RIGHT_ANKLE,
            "front_depth": right_depth,
            "back_depth": left_depth,
            "front_vis": right_vis
        }
    else:
        return {
            "side": "LEFT",
            "S": mp_pose.PoseLandmark.LEFT_SHOULDER,
            "H": mp_pose.PoseLandmark.LEFT_HIP,
            "K": mp_pose.PoseLandmark.LEFT_KNEE,
            "A": mp_pose.PoseLandmark.LEFT_ANKLE,
            "front_depth": left_depth,
            "back_depth": right_depth,
            "front_vis": left_vis
        }

# ==================== Kamera =======================
if USE_PHONE_CAMERA:
    cap = cv2.VideoCapture(PHONE_CAM_URL)
    camera_name = f"Telefon kamerası: {PHONE_CAM_URL}"
else:
    cap = cv2.VideoCapture(PC_CAMERA_INDEX)
    camera_name = f"Bilgisayar kamerası index: {PC_CAMERA_INDEX}"

if not cap.isOpened():
    print("Kamera açılamadı!")
    print(f"Seçilen kaynak: {camera_name}")
    print("Telefon kamerası kullanıyorsan telefon ve bilgisayarın aynı Wi-Fi ağında olduğundan emin ol.")
    print("IP Webcam/DroidCam uygulamasındaki adresi PHONE_CAM_URL içine doğru yaz.")
    csv_file.close() if 'csv_file' in globals() and not csv_file.closed else None
    exit()

print(f"✅ Kamera kaynağı açıldı: {camera_name}")
write_status("CAMERA_OPENED_RUNNING")

# ==================== Kamera Kaydı =================
video_writer = None
video_output_path = None

def safe_username(name):
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(name))

def init_video_writer(first_frame):
    global video_writer, video_output_path
    if not SAVE_CAMERA_RECORDING:
        return

    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uname = safe_username(login.username)
    video_output_path = os.path.join(
        VIDEO_OUTPUT_DIR,
        f"kamera_kaydi_{uname}_{timestamp}{VIDEO_EXTENSION}"
    )

    h, w = first_frame.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
    video_writer = cv2.VideoWriter(video_output_path, fourcc, VIDEO_FPS, (w, h))

    if not video_writer.isOpened():
        print("⚠️ Video kaydı başlatılamadı. Codec/uzantı uyumsuz olabilir.")
        print("   Çözüm: VIDEO_CODEC='XVID' ve VIDEO_EXTENSION='.avi' deneyebilirsin.")
        video_writer = None
        video_output_path = None
    else:
        print(f"🎥 Kamera kaydı başladı: {video_output_path}")

# ==================== Veri & Zaman =================
t0              = time.time()
last_sample_time = 0.0

hip_buf   = deque(maxlen=BUFFER_SIZE)
knee_buf  = deque(maxlen=BUFFER_SIZE)
ankle_buf = deque(maxlen=BUFFER_SIZE)

t_list, hip_list, knee_list, ankle_list = [], [], [], []

hip_offset = knee_offset = ankle_offset = None
running     = True   # MATLAB GUI BAŞLAT komutu geldiği için sistem doğrudan çalışır
frame_count = 0
low_vis_count = 0

# ==================== CSV ==========================
csv_name = "angles_data_v2.csv"
csv_file = open(csv_name, "w", newline="")
writer   = csv.writer(csv_file)
writer.writerow(["Time_s", "Hip_deg", "Knee_deg", "Ankle_deg",
                 "ActiveLeg", "ROM_Hip", "ROM_Knee", "ROM_Ankle",
                 "User", "Height_cm", "Weight_kg"])


# ==================== Ana Döngü ====================
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Kameradan görüntü alınamadı. Bağlantı/IP adresi kesilmiş olabilir.")
        break

    # Telefon kamerasından gelen görüntünün yönünü gerekirse düzelt
    if ROTATE_FRAME == "CW":
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif ROTATE_FRAME == "CCW":
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif ROTATE_FRAME == "180":
        frame = cv2.rotate(frame, cv2.ROTATE_180)

    if FLIP_FRAME_HORIZONTAL:
        frame = cv2.flip(frame, 1)

    if FRAME_RESIZE is not None:
        frame = cv2.resize(frame, FRAME_RESIZE)

    # İlk işlenmiş frame boyutuna göre video kaydını başlat
    if SAVE_CAMERA_RECORDING and video_writer is None and video_output_path is None:
        init_video_writer(frame)

    key = cv2.waitKey(1) & 0xFF

    if key == 32:       # SPACE — başlat / durdur
        running = not running
        if running:
            t0 = time.time() - (t_list[-1] if t_list else 0)
            last_sample_time = 0.0

    elif key == ord('r'):   # RESET (klavye)
        hip_offset = knee_offset = ankle_offset = None
        t_list.clear(); hip_list.clear()
        knee_list.clear(); ankle_list.clear()
        hip_buf.clear(); knee_buf.clear(); ankle_buf.clear()
        low_vis_count = 0
        # CSV dosyasını sıfırla
        csv_file.close()
        csv_file = open(csv_name, "w", newline="")
        writer = csv.writer(csv_file)
        writer.writerow(["Time_s", "Hip_deg", "Knee_deg", "Ankle_deg",
                         "ActiveLeg", "ROM_Hip", "ROM_Knee", "ROM_Ankle",
                         "User", "Height_cm", "Weight_kg"])
        running = False
        print("🔄 Klavye reset: veriler ve CSV temizlendi, bekleme modunda.")

    elif key == 27:     # ESC
        break

    # MATLAB GUI'den gelen çalışma/durdurma komutlarını kontrol et
    gui_cmd = read_command()
    if gui_cmd:
        gui_cmd_upper = gui_cmd.upper()
        if gui_cmd_upper.startswith("STOP"):
            print("■ MATLAB GUI DURDUR — bekleme moduna geçildi (ESC ile çıkış).")
            running = False
            write_status("PAUSED_BY_MATLAB_GUI")
            # Veri sıfırlama YOK: kullanıcı tekrar START'a basınca kaldığı yerden devam edebilir
        elif gui_cmd_upper.startswith("START"):
            # Verileri ve sayaçları sıfırla, sistemi başlat
            hip_offset = knee_offset = ankle_offset = None
            t_list.clear(); hip_list.clear()
            knee_list.clear(); ankle_list.clear()
            hip_buf.clear(); knee_buf.clear(); ankle_buf.clear()
            low_vis_count = 0
            t0 = time.time()
            last_sample_time = 0.0
            frame_count = 0
            # CSV dosyasını sıfırla (yeni oturum)
            csv_file.close()
            csv_file = open(csv_name, "w", newline="")
            writer = csv.writer(csv_file)
            writer.writerow(["Time_s", "Hip_deg", "Knee_deg", "Ankle_deg",
                             "ActiveLeg", "ROM_Hip", "ROM_Knee", "ROM_Ankle",
                             "User", "Height_cm", "Weight_kg"])
            running = True
            print(f"▶ MATLAB GUI BAŞLAT: {gui_cmd}")
            write_status("RUNNING")
        elif gui_cmd_upper.startswith("PAUSE"):
            running = False
            write_status("PAUSED_BY_MATLAB_GUI")
        elif gui_cmd_upper.startswith("RESET"):
            hip_offset = knee_offset = ankle_offset = None
            t_list.clear(); hip_list.clear()
            knee_list.clear(); ankle_list.clear()
            hip_buf.clear(); knee_buf.clear(); ankle_buf.clear()
            low_vis_count = 0
            t0 = time.time()
            last_sample_time = 0.0
            frame_count = 0
            # CSV dosyasını sıfırla
            csv_file.close()
            csv_file = open(csv_name, "w", newline="")
            writer = csv.writer(csv_file)
            writer.writerow(["Time_s", "Hip_deg", "Knee_deg", "Ankle_deg",
                             "ActiveLeg", "ROM_Hip", "ROM_Knee", "ROM_Ankle",
                             "User", "Height_cm", "Weight_kg"])
            running = False
            print("🔄 MATLAB GUI RESET: veriler ve CSV temizlendi, bekleme modunda.")
            write_status("RESET_BY_MATLAB_GUI")


    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = pose.process(rgb)

    if res.pose_landmarks:
        lm = res.pose_landmarks.landmark
        h, w, _ = frame.shape

        # Gövde/iskelet çizgilerini kapatmak için DRAW_FULL_BODY_LANDMARKS = False bırakıldı.
        # Açarsan eski MediaPipe tüm vücut çizimi geri gelir.
        if DRAW_FULL_BODY_LANDMARKS:
            mp_draw.draw_landmarks(
                frame, res.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                mp_draw.DrawingSpec(color=(180, 180, 180), thickness=2, circle_radius=2),
                mp_draw.DrawingSpec(color=(120, 220, 120), thickness=2)
            )

        # Önde olan bacak seçimi: z-derinlik + landmark görünürlük kontrolü
        selected_leg = select_front_leg(lm)
        side = selected_leg["side"]
        S = selected_leg["S"]
        H = selected_leg["H"]
        K = selected_leg["K"]
        A = selected_leg["A"]
        front_depth = selected_leg["front_depth"]
        back_depth = selected_leg["back_depth"]

        vis_ok = check_visibility(lm, [S, H, K, A])

        if not vis_ok:
            low_vis_count += 1
            cv2.putText(frame, "LOW VISIBILITY — FRAME SKIPPED",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
        else:
            def lm3d(idx):
                return np.array([lm[idx].x * w, lm[idx].y * h, lm[idx].z * w])

            shoulder = lm3d(S)
            hip_pt   = lm3d(H)
            knee_pt  = lm3d(K)
            ankle_pt = lm3d(A)

            sh2 = shoulder[:2].astype(int)
            hp2 = hip_pt[:2].astype(int)
            kn2 = knee_pt[:2].astype(int)
            an2 = ankle_pt[:2].astype(int)

            # Gövde çizgisi kapalı; sadece öndeki aktif bacak çizilir.
            if DRAW_TRUNK_LINE:
                cv2.line(frame, tuple(sh2), tuple(hp2), (0, 255, 0), 3)

            if DRAW_ACTIVE_LEG_LINES:
                cv2.line(frame, tuple(hp2), tuple(kn2), (0, 255, 0), 5)
                cv2.line(frame, tuple(kn2), tuple(an2), (0, 255, 0), 5)

            if DRAW_JOINT_POINTS:
                for pt in [hp2, kn2, an2]:
                    cv2.circle(frame, tuple(pt), 7, (0, 255, 255), -1)
                    cv2.circle(frame, tuple(pt), 9, (0, 0, 0), 2)

            if running:
                t_now = time.time() - t0

                trunk3      = shoulder - hip_pt
                upper_hip3  = knee_pt  - hip_pt
                upper_knee3 = hip_pt   - knee_pt
                lower_knee3 = ankle_pt - knee_pt
                lower_ank3  = knee_pt  - ankle_pt
                v_ref3      = np.array([0, -1, 0], dtype=float)

                if t_now - last_sample_time < SAMPLE_INTERVAL:
                    hip_buf.append(angle_between_3d(trunk3, upper_hip3))
                    knee_buf.append(angle_between_3d(upper_knee3, lower_knee3))
                    ankle_buf.append(angle_between_3d(lower_ank3, v_ref3))
                else:
                    last_sample_time = t_now
                    frame_count += 1

                    hip_raw   = angle_between_3d(trunk3, upper_hip3)
                    knee_raw  = angle_between_3d(upper_knee3, lower_knee3)
                    ankle_raw = angle_between_3d(lower_ank3, v_ref3)

                    hip_buf.append(hip_raw)
                    knee_buf.append(knee_raw)
                    ankle_buf.append(ankle_raw)

                    if hip_offset is None:
                        hip_offset   = hip_raw
                        knee_offset  = knee_raw
                        ankle_offset = ankle_raw

                    hip_f   = apply_butter(list(hip_buf))   - hip_offset
                    knee_f  = apply_butter(list(knee_buf))  - knee_offset
                    ankle_f = apply_butter(list(ankle_buf)) - ankle_offset

                    # Canlı eklem açılarını MATLAB GUI için geçici dosyaya yaz

                    t_list.append(t_now)
                    hip_list.append(hip_f)
                    knee_list.append(knee_f)
                    ankle_list.append(ankle_f)

                    rom_hip   = max(hip_list)   - min(hip_list)   if hip_list   else 0
                    rom_knee  = max(knee_list)  - min(knee_list)  if knee_list  else 0
                    rom_ankle = max(ankle_list) - min(ankle_list) if ankle_list else 0

                    # Canlı eklem açıları + ROM değerlerini MATLAB GUI için yaz
                    live_angles_path = os.path.join(CONTROL_DIR, "live_angles.txt")
                    try:
                        with open(live_angles_path, "w", encoding="utf-8") as f_live:
                            f_live.write(
                                f"{t_now:.3f},{hip_f:.2f},{knee_f:.2f},{ankle_f:.2f},"
                                f"{rom_hip:.1f},{rom_knee:.1f},{rom_ankle:.1f}\n"
                            )
                    except OSError:
                        pass

                    writer.writerow([
                        f"{t_now:.3f}", f"{hip_f:.2f}", f"{knee_f:.2f}", f"{ankle_f:.2f}",
                        side,
                        f"{rom_hip:.1f}", f"{rom_knee:.1f}", f"{rom_ankle:.1f}",
                        login.username, user_height, user_weight
                    ])
                    csv_file.flush()

                    if DRAW_ANGLE_ARCS:
                        draw_arc(frame, tuple(hp2), trunk3[:2], upper_hip3[:2],  35, (0,   255, 255))
                        draw_arc(frame, tuple(kn2), upper_knee3[:2], lower_knee3[:2], 35, (255, 0, 0))
                        draw_arc(frame, tuple(an2), lower_ank3[:2], v_ref3[:2]*80, 30, (255, 255, 0))

                    cv2.putText(frame,
                        f"Hip:{hip_f:+.1f}  Knee:{knee_f:+.1f}  Ankle:{ankle_f:+.1f}",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.putText(frame, f"FRONT LEG: {side}", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, f"z_front:{front_depth:+.3f}  z_back:{back_depth:+.3f}",
                    (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 255, 255), 1)


    status = "RUNNING" if running else "PAUSED"
    cv2.putText(frame, f"{status} | SPACE start/stop | R reset | ESC exit",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 0) if running else (0, 0, 255), 2)

    # Kamera kaydı: ekranda görünen işlenmiş/üzerine çizim yapılmış frame kaydedilir.
    should_record = SAVE_CAMERA_RECORDING and video_writer is not None
    if RECORD_ONLY_WHEN_RUNNING:
        should_record = should_record and running

    if should_record:
        cv2.putText(frame, "REC", (frame.shape[1] - 80, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        video_writer.write(frame)

    cv2.imshow("Front Leg Pose — No Trunk Lines + Recording", frame)

# ==================== KAPANIŞ ======================

cap.release()
if video_writer is not None:
    video_writer.release()
cv2.destroyAllWindows()
csv_file.close()


write_status("FINISHED")
print(f"\n✅ Tamamlandı.")
print(f"   CSV      : angles_data_v2.csv")
print(f"   PNG      : leg_joint_angles_v2.png")
print(f"   MATLAB   : plot_angles_matlab_v2.m")
if video_output_path:
    print(f"   Video    : {video_output_path}")
print(f"   Atlanan  : {low_vis_count} düşük görünürlük frame'i")
