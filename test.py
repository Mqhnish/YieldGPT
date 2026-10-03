"""Hackathon workflow diagram - renders cleanly in the VS Code terminal / Output panel."""
import sys
 
# Force UTF-8 so box-drawing characters display correctly (esp. on Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
 
INDENT = 4   # left margin
INNER = 58   # inner width of every box
RAIL = INDENT + INNER + 2 + 6  # column of the vertical "loop" line on the right
 
 
def box(title, bullets):
    """Return a list of lines forming a box with perfectly aligned borders."""
    top = "┌" + "─" * INNER + "┐"
    bot = "└" + "─" * INNER + "┘"
    body = [f"│{('  ' + title).ljust(INNER)}│"]
    body += [f"│{('  ' + b).ljust(INNER)}│" for b in bullets]
    return [top, *body, bot]
 
 
def indent(lines):
    return [" " * INDENT + l for l in lines]
 
 
def arrow_down():
    mid = INDENT + (INNER + 2) // 2
    return [" " * mid + "│", " " * mid + "▼"]
 
 
def main():
    out = []
    w = 74
    out += ["=" * w,
            " THE HACKATHON WORKFLOW: YOUR ITERATIVE LOOP",
            "=" * w, ""]
 
    # Step 1
    out += indent(box("1. INITIAL EXPLORATION & SETUP", [
        "- Load training data & split into Train / Validation",
        "- Build a basic pipeline to get a raw baseline score",
    ]))
    out += arrow_down()
 
    # Step 2 (loop re-enters here)
    s2 = indent(box("2. THE COMPETITIVE SPRINT", [
        "- Creative feature engineering (cyclic time, weather)",
        "- Model selection & hyperparameter tuning",
    ]))
    box_w = INDENT + INNER + 2
    s2[2] = s2[2].ljust(box_w) + "◀" + "─" * 5 + "┐"   # arrow into box (title row+1)
    for i in range(len(s2)):
        if i not in (2,):
            s2[i] = s2[i].ljust(RAIL) + ("│" if i > 2 else "")
    s2[1] = s2[1].ljust(box_w)
    s2[0] = s2[0].ljust(box_w)
    out += s2
    out += [" " * (INDENT + (INNER + 2) // 2) + "│" + " " * (RAIL - INDENT - (INNER + 2) // 2 - 1) + "│  Repeat this cycle",
            " " * (INDENT + (INNER + 2) // 2) + "▼" + " " * (RAIL - INDENT - (INNER + 2) // 2 - 1) + "│  to drop your RMSE!"]
 
    # Step 3
    s3 = indent(box("3. METRIC EVALUATION", [
        "- Check your validation scorecard (RMSE, MAE, R²)",
    ]))
    out += [l.ljust(RAIL) + "│" for l in s3]
    mid = INDENT + (INNER + 2) // 2
    out += [" " * mid + "│" + " " * (RAIL - mid - 1) + "│",
            " " * mid + "▼" + " " * (RAIL - mid - 1) + "│"]
    out += [("    Is your validation RMSE improving?").ljust(RAIL) + "│"]
    out += [(" " * mid + "│").ljust(RAIL) + "│"]
    out += [(" " * mid + "├─── [ NO ] ").ljust(RAIL - 1, "─") + "─┘",
            " " * mid + "│    (go back, fix features, try new models)"]
    out += [" " * mid + "└─── [ YES! ]",
            " " * (mid + 5) + "│",
            " " * (mid + 5) + "▼"]
 
    # Step 4 - shift box so its centre lines up with the YES arrow
    s4 = box("4. THE FINAL DELIVERABLE", [
        "- Predict on the hidden test features (X_test)",
        "- Export with submission_df.to_csv('submission.csv')",
        "- Upload to the leaderboard and secure your rank!",
    ])
    shift = (mid + 5) - (INNER + 2) // 2
    out += [" " * shift + l for l in s4]
 
    out += ["", "=" * w,
            "TIP: Stay locked in the loop between Steps 2 & 3!",
            "Never submit blindly: tweak features -> check score locally -> win!",
            "=" * w]
    print("\n".join(out))
 
 
if __name__ == "__main__":
    main()