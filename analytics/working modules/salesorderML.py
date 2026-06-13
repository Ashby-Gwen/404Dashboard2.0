import os
import glob
import json
import threading
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from dotenv import load_dotenv

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, InvalidArgument
from tabulate import tabulate

# 1. Load Environment Variables
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    messagebox.showerror("Configuration Error", "GEMINI_API_KEY not found. Please check your .env file.")
    exit()

genai.configure(api_key=API_KEY)

class InvoiceExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel to Record Invoice Extractor")
        self.root.geometry("800x600")
        
        self.folder_path = tk.StringVar()
        self.selected_model = tk.StringVar(value="gemini-2.5-flash")
        
        # Available models
        self.available_models = [
            "gemini-2.5-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "ashby"
        ]
        
        self.setup_ui()

    def setup_ui(self):
        # --- Top Frame: Inputs ---
        input_frame = ttk.LabelFrame(self.root, text="Configuration", padding=(10, 10))
        input_frame.pack(fill="x", padx=10, pady=10)

        # Folder Selection
        ttk.Label(input_frame, text="Target Folder:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.folder_path, width=60).grid(row=0, column=1, padx=10, pady=5)
        ttk.Button(input_frame, text="Browse", command=self.browse_folder).grid(row=0, column=2, pady=5)

        # Model Selection
        ttk.Label(input_frame, text="Gemini Model:").grid(row=1, column=0, sticky="w", pady=5)
        model_dropdown = ttk.Combobox(input_frame, textvariable=self.selected_model, values=self.available_models, state="readonly", width=30)
        model_dropdown.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # --- Middle Frame: Controls & Progress ---
        control_frame = ttk.Frame(self.root, padding=(10, 5))
        control_frame.pack(fill="x", padx=10)

        self.start_btn = ttk.Button(control_frame, text="Start Extraction", command=self.start_extraction)
        self.start_btn.pack(side="left", pady=5)

        self.progress = ttk.Progressbar(control_frame, orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10, pady=5)

        # --- Bottom Frame: Logs/Errors ---
        log_frame = ttk.LabelFrame(self.root, text="Console Logs & Errors", padding=(10, 10))
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_area = ScrolledText(log_frame, state="disabled", font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.log_area.pack(fill="both", expand=True)

    def log(self, message, msg_type="info"):
        """Thread-safe logging to the text area."""
        self.log_area.config(state="normal")
        
        # Simple color coding for errors vs info
        tags = {"error": "red", "success": "green", "info": "white", "warning": "yellow"}
        self.log_area.tag_config(msg_type, foreground=tags.get(msg_type, "white"))
        
        self.log_area.insert("end", message + "\n", msg_type)
        self.log_area.see("end")
        self.log_area.config(state="disabled")

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select Folder containing Excel files")
        if folder:
            self.folder_path.set(folder)

    def start_extraction(self):
        path = self.folder_path.get()
        if not path:
            messagebox.showwarning("Missing Input", "Please select a folder first.")
            return

        self.start_btn.config(state="disabled")
        self.progress["value"] = 0
        self.log_area.config(state="normal")
        self.log_area.delete("1.0", "end")
        self.log_area.config(state="disabled")
        
        # Run extraction in a background thread to keep UI responsive
        threading.Thread(target=self.process_files, args=(path,), daemon=True).start()

    def process_files(self, folder_path):
        self.log("="*60, "info")
        self.log(f"📊 STARTING BATCH EXTRACTION", "info")
        self.log("="*60, "info")

        search_pattern = os.path.join(folder_path, "*.xlsx")
        file_list = glob.glob(search_pattern)

        if not file_list:
            self.log(f"⚠️ No .xlsx files found in: {folder_path}", "warning")
            self.reset_ui()
            return

        self.log(f"Found {len(file_list)} files. Using model: {self.selected_model.get()}\n", "info")
        
        try:
            model = genai.GenerativeModel(
                self.selected_model.get(),
                generation_config={"response_mime_type": "application/json"}
            )
        except Exception as e:
            self.log(f"❌ Failed to load model: {e}", "error")
            self.reset_ui()
            return

        self.progress["maximum"] = len(file_list)
        all_extracted_data = []

        for i, filepath in enumerate(file_list):
            filename = os.path.basename(filepath)
            self.log(f"⏳ Scanning: {filename}...", "info")
            
            try:
                # Read Excel with 55x20 safety margin
                df_raw = pd.read_excel(filepath)
                df_subset = df_raw.iloc[:55, :20] 
                csv_context = df_subset.to_csv(index=False)
                
                prompt = f"""
                You are a data extraction AI. I am providing you with raw, potentially messy tabular data exported to CSV from an Excel file.
                Identify the pattern of the records and extract the following information for every valid transaction found:

                1. Store Name
                2. Branch
                3. Invoice Type (Analyze the context and strictly classify as 'Service Invoice' or 'Sales Invoice')
                4. Date
                5. Amount (The total revenue amount)
                6. Sales Staff (Identify the name of the staff member responsible)

                Return the extracted data STRICTLY as a JSON array of objects. Use these exact keys:
                "store_name", "branch", "invoice_type", "date", "amount", "sales_staff"

                Ignore empty rows, headers, or irrelevant metadata. Only output the JSON array.

                Raw Data Context:
                {csv_context}
                """

                response = model.generate_content(prompt)
                extracted_json = json.loads(response.text)
                
                if extracted_json:
                    for record in extracted_json:
                        record['source_file'] = filename
                    all_extracted_data.extend(extracted_json)
                    self.log(f"  ✅ Extracted {len(extracted_json)} revenue records.\n", "success")
                else:
                    self.log(f"  ⚠️ No valid records found.\n", "warning")
                    
            except ResourceExhausted:
                self.log(f"  ❌ API Quota/Rate Limit Exceeded while processing {filename}. Consider switching models or waiting.", "error")
            except ServiceUnavailable:
                self.log(f"  ❌ Google API Service Unavailable while processing {filename}. Check your connection.", "error")
            except json.JSONDecodeError:
                self.log(f"  ❌ Model failed to return valid JSON for {filename}.", "error")
            except Exception as e:
                self.log(f"  ❌ Error processing {filename}: {e}\n", "error")

            # Update progress bar
            self.progress["value"] = i + 1
            self.root.update_idletasks()

        # Combine, Format, and Export
        if all_extracted_data:
            df_combined = pd.DataFrame(all_extracted_data)
            excel_filename = "Record_Invoice_Feed.xlsx"
            csv_filename = "Record_Invoice_Feed.csv"
            
            df_combined.to_excel(excel_filename, index=False)
            df_combined.to_csv(csv_filename, index=False)
            
            self.log("="*60, "success")
            self.log("✅ BATCH EXTRACTION COMPLETE", "success")
            self.log("="*60, "success")
            self.log(f"Total records ready for dashboard integration: {len(df_combined)}", "info")
            self.log(f"Files saved locally as '{excel_filename}' and '{csv_filename}'.\n", "info")
        else:
            self.log("\n⚠️ No data was extracted from any of the files.", "warning")

        self.reset_ui()

    def reset_ui(self):
        """Re-enables the start button after processing is done."""
        self.start_btn.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    
    # Optional: Apply a cleaner theme if available
    style = ttk.Style()
    if 'clam' in style.theme_names():
        style.theme_use('clam')
        
    app = InvoiceExtractorApp(root)
    root.mainloop()