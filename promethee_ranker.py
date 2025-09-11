
import pandas as pd

# V-shape preference function
def preference(a, b, direction):
    diff = a - b if direction == 'max' else b - a
    return max(0, diff)

def main():
    """Main function to apply PROMETHEE ranking to vehicle listings."""
    
    # Load data
    df = pd.read_csv(r"Output\used_cars_with_pareto_by_model.csv")

    # Clean mileage if needed
    df['mileage'] = df['mileage'].replace('[^0-9]', '', regex=True).astype(float)

    # Define PROMETHEE weights and directions
    weights = {
        'price': 0.4,
        'mileage': 0.15,
        'model_year': 0.1,
        'mpg': 0.05,
        'condition_rating': 0.05,
        'title_type': 0.15,
        'avg_yearly_mileage': 0.1
    }

    directions = {
        'price': 'min',
        'mileage': 'min',
        'model_year': 'max',
        'mpg': 'max',
        'condition_rating': 'max',
        'title_type': 'max',
        'avg_yearly_mileage': 'max'
    }

    # Apply PROMETHEE II per brand+model group
    df['promethee_net_flow'] = float('nan')

    for (brand, model), group in df.groupby(['brand', 'model']):
        indices = group.index
        n = len(indices)
        if n < 2:
            df.loc[indices, 'promethee_net_flow'] = 0
            continue
        preference_matrix = pd.DataFrame(0, index=indices, columns=indices, dtype=float)
        # Compute pairwise preference scores
        for i in indices:
            for j in indices:
                if i == j:
                    continue
                score = 0
                for crit in weights:
                    p = preference(df.at[i, crit], df.at[j, crit], directions[crit])
                    score += weights[crit] * p
                preference_matrix.at[i, j] = score
        # Compute flows
        pos_flow = preference_matrix.sum(axis=1) / (n - 1)
        neg_flow = preference_matrix.sum(axis=0) / (n - 1)
        net_flow = pos_flow - neg_flow
        df.loc[indices, 'promethee_net_flow'] = net_flow

    # Rank cars within each (brand, model) group based on PROMETHEE net flow (higher is better)
    df['promethee_rank'] = df.groupby(['brand', 'model'])['promethee_net_flow'].rank(method='dense', ascending=False)

    df = df.sort_values(by=['brand','model','promethee_rank','model_year'])
    # Save result
    df.to_csv(r"Output\used_cars_promethee_ranked.csv", index=False)


if __name__ == "__main__":
    main()
