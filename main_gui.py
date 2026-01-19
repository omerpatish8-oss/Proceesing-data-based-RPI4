import tkinter as tk
from tkinter import messagebox
import os
import motor_control
import esp32_comm
import data_processor

class RpiProjectGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("מערכת ניהול פרויקט - RPI & ESP32")
        self.root.geometry("450x450")
        self.root.configure(bg="#f0f0f0")

        # כותרת הממשק
        self.label = tk.Label(root, text="ממשק שליטה ועיבוד אותות", font=("Arial", 16, "bold"), bg="#f0f0f0")
        self.label.pack(pady=20)

        # כפתור 1: הפעלת מנוע
        self.btn_motor = tk.Button(root, text="1. הפעלת מנוע (PWM)", 
                                  command=self.handle_motor, width=30, height=2, 
                                  bg="#007bff", fg="white", font=("Arial", 10, "bold"))
        self.btn_motor.pack(pady=10)

        # כפתור 2: מוכנות לקבלת מידע מה-ESP32
        self.btn_esp = tk.Button(root, text="2. מוכנות לקליטה מ-ESP32", 
                                command=self.handle_esp, width=30, height=2, 
                                bg="#28a745", fg="white", font=("Arial", 10, "bold"))
        self.btn_esp.pack(pady=10)

        # כפתור 3: ניתוח נתונים
        self.btn_analysis = tk.Button(root, text="3. התחלת ניתוח נתונים", 
                                     command=self.handle_analysis, width=30, height=2, 
                                     bg="#ffc107", font=("Arial", 10, "bold"))
        self.btn_analysis.pack(pady=10)

        # תיבת סטטוס
        self.status_label = tk.Label(root, text="סטטוס: ממתין לפקודה", font=("Arial", 10), bg="#f0f0f0")
        self.status_label.pack(pady=20)

    def handle_motor(self):
        self.status_label.config(text="סטטוס: מנוע בפעולה...")
        motor_control.start_motor_logic()
        messagebox.showinfo("מנוע", "נשלחה פקודה להפעלת המנוע.")

    def handle_esp(self):
        self.status_label.config(text="סטטוס: שולח סיגנל ל-ESP32...")
        # שליחת תו "2" ל-ESP32 דרך ה-Serial
        success = esp32_comm.send_ready_signal()
        if success:
            messagebox.showinfo("ESP32", "הפאי מוכן. ה-ESP32 קיבל את הפקודה.")
        else:
            messagebox.showerror("שגיאה", "נכשל החיבור ל-ESP32 דרך USB.")

    def handle_analysis(self):
        self.status_label.config(text="סטטוס: מנתח נתונים...")
        if os.path.exists("recorded_data.csv"):
            data_processor.run_analysis()
            messagebox.showinfo("ניתוח", "הניתוח הסתיים בהצלחה.")
        else:
            messagebox.showwarning("שגיאה", "לא נמצא קובץ נתונים (recorded_data.csv).")

if __name__ == "__main__":
    root = tk.Tk()
    app = RpiProjectGUI(root)
    root.mainloop()
