import pandas as pd
from datetime import datetime
import numpy as np
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut
import argparse

# Step 1: Load the dataset
df = pd.read_csv(r'screenshots\structured_results.csv')

def _parse_args():
    p = argparse.ArgumentParser(description="Pareto Finder")
    p.add_argument("--user-city", default=None, help="City of the User")
    return p.parse_args()

args = _parse_args()

USER_CITY = args.user_city if args.user_city else 'Chicago, IL'

# Clean mileage
df['mileage'] = df['mileage'].replace('[^0-9]', '', regex=True)
df['mileage'] = df['mileage'].replace('', np.nan)  # Replace empty strings with NaN
df['mileage'] = df['mileage'].astype(float)
s = df['listed_days_ago'].astype(str).str.replace(r'[^0-9.]', '', regex=True)
df['listed_days_ago'] = pd.to_numeric(s, errors='coerce')  # '' -> NaN

df['listed_days_ago'] = (pd.Timestamp.now() - pd.to_datetime(df['run_ts'])).dt.days +df['listed_days_ago'].fillna(1)
# Initialize is_pareto column
df['is_pareto'] = False
df['model'] = df.model.str.split(' ',n=1, expand =True)[0].str.lower()
df['brand'] = df.brand.str.lower()

def convert_year(val):
    if isinstance(val, str) and '-' in val:
        start, end = val.split('-')
        return (float(start) + float(end)) / 2
    try:
        return float(val)
    except:
        return np.nan

df['model_year'] = df['model_year'].apply(convert_year)

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


# Criteria directions
criteria = {
    'price': 'min',
    'mileage': 'min',
    'model_year': 'max',
    'mpg': 'max',
    'condition_rating': 'max',
    'title_type': 'max'
}


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


# Apply Pareto filtering within each brand+model group
# criteria example: {"price":"min", "mileage":"min", "year":"max"}
df['is_pareto'] = False  # init

for (brand, model), group in df.groupby(['brand', 'model'], sort=False):
    mask = pareto_front_mask(group, criteria, eps=1e-9)  # True = non-dominated
    df.loc[group.index, 'is_pareto'] = mask


# Calculate average yearly mileage
df['model_year'] = pd.to_numeric(df['model_year'], errors='coerce')

df['avg_yearly_mileage'] = df['mileage'] / (datetime.now().year - df['model_year'])
df['avg_yearly_mileage'] = df['avg_yearly_mileage'].replace(np.inf, np.nan).fillna((datetime.now().year - df['model_year'])*12000)
# Create mileage_suspect column
df['mileage_suspect'] = (df['avg_yearly_mileage'] < 7000).astype(int)

df['seller_type'] = df['image'].str.split('_', n=1, expand=True)[0].replace('listing', value=np.nan)


# PERSONAL FILTERS
# df = df[df['mileage_suspect']==0]
# df = df[df['listed_days_ago']<=6]

# df_sub = df[(df['price']>=3500)&(df['price']<=6000)]
# df_sub = df_sub[(df_sub['model_year']>2012)]
# df_sub = df_sub[(df_sub['mileage']<120000)]


# Save or use result
df.to_csv(r"Output\used_cars_with_pareto_by_model.csv", index=False)

