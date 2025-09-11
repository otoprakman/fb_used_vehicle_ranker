import pandas as pd
from datetime import datetime
import numpy as np
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut
import os
try:
    from dotenv import load_dotenv
    load_dotenv("creds.env", override=True)
except Exception:
    pass

def convert_year(val):
    if isinstance(val, str) and '-' in val:
        start, end = val.split('-')
        return (float(start) + float(end)) / 2
    try:
        return float(val)
    except:
        return np.nan

def pareto_front_mask(df, criteria, eps=0.0):
    cols = list(criteria.keys())
    sign = np.array([-1 if d=='min' else 1 for d in criteria.values()], dtype=float)
    X = df[cols].to_numpy(dtype=float) * sign  # convert to all-maximize
    n = len(df)
    dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        if dominated[i]: 
            continue
        better_or_equal = (X >= X[i] - eps).all(axis=1)
        strictly_better = (X >  X[i] + eps).any(axis=1)
        dominated |= better_or_equal & strictly_better
    return ~dominated  # True = on Pareto front

def main(user_city=None):
    """Main function to find Pareto-optimal product listings."""
    USER_CITY = user_city or os.getenv("USER_CITY") or 'Chicago, IL'
    
    # Step 1: Load the dataset
    df = pd.read_csv(r'screenshots\structured_results.csv')

    # Clean numeric fields
    s = df['listed_days_ago'].astype(str).str.replace(r'[^0-9.]', '', regex=True)
    df['listed_days_ago'] = pd.to_numeric(s, errors='coerce')  # '' -> NaN

    df['listed_days_ago'] = (pd.Timestamp.now() - pd.to_datetime(df['run_ts'])).dt.days +df['listed_days_ago'].fillna(1)
    # Initialize is_pareto column
    df['is_pareto'] = False
    
    # Clean generic fields
    if 'brand' in df.columns:
        df['brand'] = df['brand'].str.lower()
    if 'category' in df.columns:
        df['category'] = df['category'].str.lower()

    df.columns = df.columns.str.lower()


    # Initialize geolocator
    geolocator = Nominatim(user_agent="myGeocoder", timeout=10)

    # Geocode the specific location (for reference point)
    location_ref = geolocator.geocode(USER_CITY)
    lat_ref, lon_ref = location_ref.latitude, location_ref.longitude

    unique_cities = df['location'].unique()
    # Create a dictionary to store city -> (lat, lon)
    city_coords = {}

    # Function to geocode and store results
    def get_city_coords(city):
        if city not in city_coords:
            try:
                location = geolocator.geocode(city)
                if location:
                    city_coords[city] = (location.latitude, location.longitude)
                else:
                    city_coords[city] = (None, None)
            except GeocoderTimedOut:
                city_coords[city] = (None, None)
                print(f"Geocoding timed out for {city}")
        return city_coords[city]

    # Geocode all unique cities
    for idx,city in enumerate(unique_cities):
        print(f'{idx}/{len(unique_cities)}')
        get_city_coords(city)

    # Function to calculate distance for each row
    def calculate_distance(city):
        lat, lon = city_coords.get(city, (None, None))
        if lat and lon:
            return geodesic((lat_ref, lon_ref), (lat, lon)).miles  # distance in kilometers
        return None

    # Apply the distance calculation to the original DataFrame
    df['distance_away'] = df['location'].apply(calculate_distance)


    # Generic product criteria
    criteria = {
        'price': 'min',           # Lower price is better
        'condition_rating': 'max' # Higher condition rating is better
    }

    # Apply Pareto filtering within each category group
    df['is_pareto'] = False  # init

    # Group by category if available, otherwise treat all as one group
    if 'category' in df.columns and not df['category'].isna().all():
        for category, group in df.groupby(['category'], sort=False):
            mask = pareto_front_mask(group, criteria, eps=1e-9)  # True = non-dominated
            df.loc[group.index, 'is_pareto'] = mask
    else:
        # If no category, apply to entire dataset
        mask = pareto_front_mask(df, criteria, eps=1e-9)
        df['is_pareto'] = mask

    # Extract seller type from image filename if available
    if 'image' in df.columns:
        df['seller_type'] = df['image'].str.split('_', n=1, expand=True)[0].replace('listing', value=np.nan)

    # Save or use result
    df.to_csv(r"Output\products_with_pareto_by_category.csv", index=False)


if __name__ == "__main__":
    main()