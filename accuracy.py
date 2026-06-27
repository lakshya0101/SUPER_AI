import pandas as pd

df = pd.read_excel("output_results_20260610_155144.xlsx")

result_col = "Result"

total = len(df)

pass_count = (df[result_col].astype(str).str.upper() == "PASS").sum()
fail_count = (df[result_col].astype(str).str.upper() == "FAIL").sum()

missing_count = (
    df[result_col]
    .astype(str)
    .str.upper()
    .isin(["DATA MISSING", "DATAMISSING"])
    .sum()
)

accuracy = (pass_count / total) * 100 if total > 0 else 0

evaluated = pass_count + fail_count

evaluated_accuracy = (
    (pass_count / evaluated) * 100
    if evaluated > 0 else 0
)

print("=" * 50)
print(f"Total Questions      : {total}")
print(f"PASS                 : {pass_count}")
print(f"FAIL                 : {fail_count}")
print(f"DATA MISSING         : {missing_count}")
print(f"Overall Accuracy     : {accuracy:.2f}%")
print(f"Evaluated Accuracy   : {evaluated_accuracy:.2f}%")
print("=" * 50)