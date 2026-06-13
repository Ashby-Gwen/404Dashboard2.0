import pandas as pd
import google.generativeai as genai
from google.colab import userdata, files
import json
import os
import glob

# 1. Authenticate with Gemini API
try:
    API_KEY = userdata.get('GEMINI_API_KEY')
    genai.configure(api_key=API_KEY)
except userdata.SecretNotFoundError:
    print("Error: Please set up the 'GEMINI_API_KEY' in the Colab Secrets tab.")
    raise

# 2. Define the folder path containing your Excel files
# NOTE: Update this path to where your files are stored in Colab or Google Drive
excel_files_path = "/content/your_excel_folder/" # e.g., "/content/drive/MyDrive/Sales_Data/"

# 3. Configure Gemini API for Structured Output
model = genai.GenerativeModel('gemini-2.5-flash',
                              generation_config={"response_mime_type": "application/json"})

# Find all Excel files in the specified directory
search_pattern = os.path.join(excel_files_path, "*.xlsx")
file_list = glob.glob(search_pattern)

if not file_list:
    print(f"No .xlsx files found in the directory: {excel_files_path}")
else:
    print(f"Found {len(file_list)} files. Starting extraction...\n")

all_extracted_data = []

# 4. Loop through each file and process
for filepath in file_list:
    filename = os.path.basename(filepath)
    print(f"Processing: {filename}...")
    
    try:
        # Read the Excel sheet with safety margins (55 rows, 20 columns)
        df_raw = pd.read_excel(filepath)
        df_subset = df_raw.iloc[:55, :20] 
        csv_context = df_subset.to_csv(index=False)
        
        # Prepare the prompt
        prompt = f"""
        You are a data extraction AI. I am providing you with raw, potentially messy tabular data exported to CSV from an Excel file.
        Identify the pattern of the records and extract the following information for every valid transaction found:

        1. Store Name
        2. Branch
        3. Invoice Type (Analyze the context and strictly classify as 'Service Invoice' or 'Sales Invoice')
        4. Date
        5. Amount (The sales order or revenue amount)
        6. Sales Staff (Identify the name of the staff member responsible)

        Return the extracted data STRICTLY as a JSON array of objects. Use these exact keys:
        "store_name", "branch", "invoice_type", "date", "amount", "sales_staff"

        Ignore empty rows, headers, or irrelevant metadata. Only output the JSON array.

        Raw Data Context:
        {csv_context}
        """

        # Call Gemini API
        response = model.generate_content(prompt)
        
        # Parse response
        extracted_json = json.loads(response.text)
        
        if extracted_json:
            # Add a source column so you know which file each record came from
            for record in extracted_json:
                record['source_file'] = filename
            
            all_extracted_data.extend(extracted_json)
            print(f"  -> Extracted {len(extracted_json)} records from {filename}.")
        else:
            print(f"  -> No valid records found in {filename}.")
            
    except Exception as e:
        print(f"  -> Error processing {filename}: {e}")

# 5. Combine and Export Data
if all_extracted_data:
    # Convert the combined JSON array into a clean Pandas DataFrame
    df_combined = pd.DataFrame(all_extracted_data)
    
    # Export the combined data
    excel_filename = "Combined_Record_Invoice_Feed.xlsx"
    csv_filename = "Combined_Record_Invoice_Feed.csv"
    
    df_combined.to_excel(excel_filename, index=False)
    df_combined.to_csv(csv_filename, index=False)
    
    print("\n✅ Batch Extraction Successful!")
    print(f"Total records extracted: {len(df_combined)}")
    print("\nPreview of combined data:")
    display(df_combined.head())
    
    # Trigger downloads
    files.download(excel_filename)
    files.download(csv_filename)
else:
    print("\nNo data was extracted from any of the files.")