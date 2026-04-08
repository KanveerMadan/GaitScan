import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import os

def generate_plots(df, output_dir="outputs"):
    os.makedirs(output_dir, exist_ok=True)

    # 1. Knee angles over time
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df["time_s"], df["knee_L"], label="Left knee",  color="#378ADD", linewidth=1.5)
    ax.plot(df["time_s"], df["knee_R"], label="Right knee", color="#D85A30", linewidth=1.5, alpha=0.85)
    ax.axhline(170, color="gray", linestyle="--", alpha=0.4, label="Full extension (170°)")
    ax.fill_between(df["time_s"], df["knee_L"], df["knee_R"], alpha=0.08, color="purple", label="L/R difference")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Angle (degrees)")
    ax.set_title("Knee Flexion — Left vs Right")
    ax.legend()
    ax.set_ylim(60, 200)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/knee_angles.png", dpi=150)
    plt.close()
    print(f"  Saved: {output_dir}/knee_angles.png")

    # 2. Hip angles over time
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df["time_s"], df["hip_L"], label="Left hip",  color="#1D9E75", linewidth=1.5)
    ax.plot(df["time_s"], df["hip_R"], label="Right hip", color="#D4537E", linewidth=1.5, alpha=0.85)
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Angle (degrees)")
    ax.set_title("Hip Flexion — Left vs Right")
    ax.legend()
    ax.set_ylim(80, 200)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/hip_angles.png", dpi=150)
    plt.close()
    print(f"  Saved: {output_dir}/hip_angles.png")

    # 3. Ankle trajectory — proves the cyclic walking pattern
    fig, ax = plt.subplots(figsize=(10, 4))
    sc = ax.scatter(df["lm27_x"], df["lm27_y"], c=df["time_s"], cmap="viridis", s=3)
    plt.colorbar(sc, label="Time (s)")
    ax.invert_yaxis()
    ax.set_xlabel("X position (normalised)")
    ax.set_ylabel("Y position (normalised)")
    ax.set_title("Left Ankle Trajectory — Walking Cycle")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/ankle_trajectory.png", dpi=150)
    plt.close()
    print(f"  Saved: {output_dir}/ankle_trajectory.png")

    # 4. Symmetry summary bar chart
    metrics = ["Knee avg", "Knee min", "Hip avg", "Hip min"]
    left_vals  = [df["knee_L"].mean(), df["knee_L"].min(), df["hip_L"].mean(), df["hip_L"].min()]
    right_vals = [df["knee_R"].mean(), df["knee_R"].min(), df["hip_R"].mean(), df["hip_R"].min()]

    x = range(len(metrics))
    fig, ax = plt.subplots(figsize=(9, 4))
    bars_l = ax.bar([i - 0.2 for i in x], left_vals,  width=0.38, label="Left",  color="#378ADD", alpha=0.85)
    bars_r = ax.bar([i + 0.2 for i in x], right_vals, width=0.38, label="Right", color="#D85A30", alpha=0.85)
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics)
    ax.set_ylabel("Angle (degrees)")
    ax.set_title("Left vs Right Symmetry Summary")
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{output_dir}/symmetry_summary.png", dpi=150)
    plt.close()
    print(f"  Saved: {output_dir}/symmetry_summary.png")

    print(f"\n  All 4 plots saved to {output_dir}/")