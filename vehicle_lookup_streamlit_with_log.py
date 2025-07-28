
import streamlit as st
import pandas as pd
import numpy as np
from rapidfuzz import process, fuzz
from datetime import datetime
import os

# Load data
vehicle_data = pd.read_csv("Cleaned_Vehicle_Dataset.csv")
vin_year_lookup = pd.read_csv("year_code_lookup.csv")
vin_year_dict = dict(zip(vin_year_lookup["Code"], vin_year_lookup["Year"]))

vehicle_data["brand"] = vehicle_data["brand"].astype(str).str.lower()
vehicle_data["model"] = vehicle_data["model"].astype(str).str.lower()

def extract_year_from_vin(vin):
    if not isinstance(vin, str) or len(vin) < 10:
        return None
    year_code = vin[9].upper()
    return vin_year_dict.get(year_code)

def normalize_entry(value):
    if pd.isna(value):
        return None
    return str(value).strip().lower()

def fuzzy_match_model(brand, model, df):
    candidates = df[df["brand"] == brand]["model"].unique()
    if len(candidates) == 0:
        return None
    best_match, score, _ = process.extractOne(model, candidates, scorer=fuzz.ratio)
    return best_match if score >= 70 else None

def lookup_vehicle(df, brand, model, year):
    brand = normalize_entry(brand)
    model = normalize_entry(model)
    try:
        year = int(year)
    except:
        return None

    model = fuzzy_match_model(brand, model, df)
    if model is None:
        return None

    match = df[
        (df["brand"] == brand) &
        (df["model"] == model) &
        (df["year"] == year)
    ]
    if not match.empty:
        return match.iloc[0].to_dict()
    return None

def suggest_closest_year_match(brand, model, year, data):
    brand = normalize_entry(brand)
    model = normalize_entry(model)
    try:
        year = int(year)
    except:
        return None

    model = fuzzy_match_model(brand, model, data)
    if model is None:
        return None

    filtered = data[
        (data["brand"] == brand) &
        (data["model"] == model) &
        (data["year"].notna())
    ]
    if filtered.empty:
        return None

    filtered["year_diff"] = abs(filtered["year"] - year)
    top_match = filtered.sort_values("year_diff").iloc[0]
    return top_match.to_dict()

def log_missing_entry(entry_dict):
    log_file = "missing_log.csv"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_dict["timestamp"] = timestamp
    file_exists = os.path.isfile(log_file)
    df = pd.DataFrame([entry_dict])
    df.to_csv(log_file, mode='a', header=not file_exists, index=False)

# Streamlit UI
st.title("🚗  Vehicle Info Lookup")

st.sidebar.header("Vehicle Query")
brand = st.sidebar.text_input("Brand", value="Audi")
model = st.sidebar.text_input("Model", value="A3")
vin_or_year = st.sidebar.text_input("VIN or Year", value="WAUZZZF46GA012345")

if st.sidebar.button("Lookup Vehicle"):
    year = None
    if vin_or_year.isdigit() and len(vin_or_year) == 4:
        year = int(vin_or_year)
    else:
        year = extract_year_from_vin(vin_or_year)

    if not year:
        st.error("❌ Could not determine year from input.")
    else:
        result = lookup_vehicle(vehicle_data, brand, model, year)
        if result:
            st.success("✅ Vehicle found:")
            st.json(result)
        else:
            suggestion = suggest_closest_year_match(brand, model, year, vehicle_data)
            if suggestion:
                st.warning(f"⚠️ Closest year match used instead of {year}:")
                st.json(suggestion)
            else:
                st.error("❌ No matching vehicle found.")
                log_missing_entry({
                    "brand": brand,
                    "model": model,
                    "vin_or_year": vin_or_year,
                    "reason": "No match found"
                })

# CSV Upload
st.header("📁 Batch Lookup via CSV")
uploaded_file = st.file_uploader("Upload a CSV with 'brand', 'model', and 'vin' or 'year' columns")

if uploaded_file is not None:
    input_df = pd.read_csv(uploaded_file)
    results = []
    stats = {"exact": 0, "fallback": 0, "not_found": 0}

    for _, row in input_df.iterrows():
        brand = normalize_entry(row.get("brand"))
        model = normalize_entry(row.get("model"))
        year = row.get("year")
        vin = row.get("vin")

        if not brand or not model:
            results.append({"Result": "Not enough info"})
            stats["not_found"] += 1
            log_missing_entry({
                "brand": brand or "",
                "model": model or "",
                "vin": vin or "",
                "year": year or "",
                "reason": "Missing brand or model"
            })
            continue

        if pd.notna(year):
            try:
                year = int(year)
            except:
                year = None
        elif pd.notna(vin):
            year = extract_year_from_vin(vin)
        else:
            year = None

        if year:
            result = lookup_vehicle(vehicle_data, brand, model, year)
            if result:
                stats["exact"] += 1
                results.append(result)
            else:
                suggestion = suggest_closest_year_match(brand, model, year, vehicle_data)
                if suggestion:
                    suggestion["Note"] = f"Closest year match used instead of {year}"
                    stats["fallback"] += 1
                    results.append(suggestion)
                else:
                    results.append({"Result": "Not enough info"})
                    stats["not_found"] += 1
                    log_missing_entry({
                        "brand": brand,
                        "model": model,
                        "vin": vin or "",
                        "year": year,
                        "reason": "No match found"
                    })
        else:
            results.append({"Result": "Not enough info"})
            stats["not_found"] += 1
            log_missing_entry({
                "brand": brand,
                "model": model,
                "vin": vin or "",
                "year": year or "",
                "reason": "No valid VIN or year"
            })

    output_df = pd.DataFrame(results)

    # Summary Stats
    st.subheader("📊 Summary")
    total = stats["exact"] + stats["fallback"] + stats["not_found"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", total)
    col2.metric("Exact Matches", stats["exact"])
    col3.metric("Fallbacks", stats["fallback"])
    col4.metric("Not Found", stats["not_found"])

    # Display and export
    st.write("🔍 Lookup Results")
    st.dataframe(output_df)
    st.download_button("Download Results as CSV", output_df.to_csv(index=False), file_name="vehicle_lookup_results.csv")
