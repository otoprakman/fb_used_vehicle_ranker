
import pandas as pd

# V-shape preference function
def preference(a, b, direction):
    diff = a - b if direction == 'max' else b - a
    return max(0, diff)

def main():
    """Main function to apply PROMETHEE ranking to product listings."""
    
    # Load data
    df = pd.read_csv(r"Output\products_with_pareto_by_category.csv")

    # Define PROMETHEE weights and directions for generic products
    weights = {
        'price': 0.6,           # Price is most important for general products
        'condition_rating': 0.4 # Condition is secondary
    }

    directions = {
        'price': 'min',         # Lower price is better
        'condition_rating': 'max' # Higher condition rating is better
    }

    # Apply PROMETHEE II per category group
    df['promethee_net_flow'] = float('nan')

    for category, group in df.groupby(['category']):
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

    # Rank products within each category group based on PROMETHEE net flow (higher is better)
    df['promethee_rank'] = df.groupby(['category'])['promethee_net_flow'].rank(method='dense', ascending=False)

    df = df.sort_values(by=['category','promethee_rank','price'])
    # Save result
    df.to_csv(r"Output\products_promethee_ranked.csv", index=False)


if __name__ == "__main__":
    main()
