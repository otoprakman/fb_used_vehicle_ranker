import pandas as pd
from datetime import datetime
import numpy as np
# Step 1: Load the dataset
df = pd.read_csv(r'screenshots\structured_results.csv')

# Clean mileage
df['mileage'] = df['mileage'].replace('[^0-9]', '', regex=True)
df['mileage'] = df['mileage'].replace('', np.nan)  # Replace empty strings with NaN
df['mileage'] = df['mileage'].astype(float)
s = df['listed_days_ago'].astype(str).str.replace(r'[^0-9.]', '', regex=True)
df['listed_days_ago'] = pd.to_numeric(s, errors='coerce')  # '' -> NaN
# Initialize is_pareto column
df['is_pareto'] = False
df['model'] = df.model.str.split(' ',n=1, expand =True)[0].str.lower()
df['brand'] = df.brand.str.lower()

df.columns = df.columns.str.lower()

# Criteria directions
criteria = {
    'price': 'min',
    'mileage': 'min',
    'model_year': 'max',
    'mpg': 'max',
    'condition_rating': 'max',
    'title_type': 'max'
}

# Dominance function
def is_dominated(row, others, criteria):
    for _, competitor in others.iterrows():
        if all(
            (competitor[c] <= row[c] if direction == 'min' else competitor[c] >= row[c])
            for c, direction in criteria.items()
        ) and any(
            (competitor[c] < row[c] if direction == 'min' else competitor[c] > row[c])
            for c, direction in criteria.items()
        ):
            return True
    return False

# Apply Pareto filtering within each brand+model group
for (brand, model), group in df.groupby(['brand', 'model']):
    indices = group.index
    for i in indices:
        row = df.loc[i]
        others = df.loc[indices].drop(i)
        if not is_dominated(row, others, criteria):
            df.at[i, 'is_pareto'] = True

# Calculate average yearly mileage
df['model_year'] = pd.to_numeric(df['model_year'], errors='coerce')

df['avg_yearly_mileage'] = df['mileage'] / (datetime.now().year - df['model_year'])

# Create mileage_suspect column
df['mileage_suspect'] = (df['avg_yearly_mileage'] < 7000).astype(int)

df = df[df['mileage_suspect']==0]
df = df[df['listed_days_ago']<=6]

# df_sub = df[(df['price']>=3500)&(df['price']<=6000)]
# df_sub = df_sub[(df_sub['model_year']>2012)]
# df_sub = df_sub[(df_sub['mileage']<120000)]

# Save or use result
df.to_csv(r"Output\used_cars_with_pareto_by_model.csv", index=False)

