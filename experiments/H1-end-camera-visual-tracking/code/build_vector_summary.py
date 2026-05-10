from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt


# 本脚本放在实验目录的 code/ 下，结果目录固定回到同级 results/。
ROOT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT_DIR / "results"
SUMMARY_DIR = RESULTS_DIR / "summary"


@dataclass
class TrialData:
    """保存单次实验的时间序列和图像误差，用于统一绘制矢量子图。"""

    position_index: int
    trial_index: int
    csv_path: Path
    time_s: list[float]
    error_x_px: list[float]
    error_y_px: list[float]


class VectorSummaryBuilder:
    """按 infer_yolo26.py 记录模块的规则，从 CSV 重绘 25 组 PDF 矢量汇总图。"""

    def __init__(self, results_dir: Path, summary_dir: Path) -> None:
        self.results_dir = results_dir
        self.summary_dir = summary_dir
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        self.trials = self._load_all_trials()

    def _load_all_trials(self) -> list[TrialData]:
        """读取固定位置 1-5 的 CSV 文件，每个位置必须包含 5 次重复实验。"""
        trials: list[TrialData] = []
        for position_index in range(1, 6):
            position_dir = self.results_dir / f"固定位置{position_index}，多次实验对比结果"
            csv_files = sorted(position_dir.glob("servo_data_*.csv"))
            if len(csv_files) != 5:
                raise RuntimeError(f"{position_dir.name} 中 CSV 数量为 {len(csv_files)}，期望 5 个")

            for trial_index, csv_path in enumerate(csv_files, start=1):
                trials.append(self._load_trial(position_index, trial_index, csv_path))
        return trials

    @staticmethod
    def _load_trial(position_index: int, trial_index: int, csv_path: Path) -> TrialData:
        """解析单个 CSV 文件，输出时间、X 方向误差和 Y 方向误差。"""
        time_s: list[float] = []
        error_x_px: list[float] = []
        error_y_px: list[float] = []

        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                time_s.append(float(row["Time(s)"]))
                error_x_px.append(float(row["ErrorX(px)"]))
                error_y_px.append(float(row["ErrorY(px)"]))

        return TrialData(
            position_index=position_index,
            trial_index=trial_index,
            csv_path=csv_path,
            time_s=time_s,
            error_x_px=error_x_px,
            error_y_px=error_y_px,
        )

    def build(self) -> None:
        """生成误差响应和图像平面轨迹两类 5x5 矢量汇总图。"""
        self._configure_matplotlib()
        self._draw_error_grid()
        self._draw_trajectory_grid()

    @staticmethod
    def _configure_matplotlib() -> None:
        """设置中文字体和 PDF 字体类型，保证论文插图可清晰缩放。"""
        plt.rcParams["font.sans-serif"] = [
            "Microsoft YaHei",
            "SimHei",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["pdf.fonttype"] = 42
        plt.rcParams["ps.fonttype"] = 42

    def _draw_error_grid(self) -> None:
        """按原记录模块样式绘制时间-像素误差曲线，红线为 ErrorX，蓝线为 ErrorY。"""
        fig, axes = plt.subplots(5, 5, figsize=(20, 12))
        for trial in self.trials:
            ax = axes[trial.position_index - 1][trial.trial_index - 1]
            ax.plot(trial.time_s, trial.error_x_px, label="Error X (px)", color="r", alpha=0.8)
            ax.plot(trial.time_s, trial.error_y_px, label="Error Y (px)", color="b", alpha=0.8)
            ax.axhline(0, color="black", linestyle="--", linewidth=1)
            ax.set_title(f"P{trial.position_index}-T{trial.trial_index}", fontsize=10)
            ax.set_xlabel("Time (s)", fontsize=8)
            ax.set_ylabel("Pixel Error (px)", fontsize=8)
            ax.legend(loc="upper right", fontsize=6)
            ax.grid(True, linestyle=":", alpha=0.7)
            ax.tick_params(labelsize=7)

            if trial.position_index == 1:
                ax.text(0.5, 1.24, f"第{trial.trial_index}次", transform=ax.transAxes, ha="center", fontsize=10)
            if trial.trial_index == 1:
                ax.text(-0.34, 0.5, f"位置{trial.position_index}", transform=ax.transAxes, va="center", fontsize=10)

        fig.suptitle("Visual Servo Tracking Error Response", fontsize=14, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.98), h_pad=1.4, w_pad=0.9)
        self._save_figure(fig, "fixed_positions_error_5x5_vector")

    def _draw_trajectory_grid(self) -> None:
        """按原记录模块样式绘制 ErrorX-ErrorY 图像平面轨迹。"""
        fig, axes = plt.subplots(5, 5, figsize=(18, 18))
        for trial in self.trials:
            ax = axes[trial.position_index - 1][trial.trial_index - 1]
            ax.plot(
                trial.error_x_px,
                trial.error_y_px,
                marker="o",
                markersize=4,
                linestyle="-",
                color="purple",
                alpha=0.6,
                label="Trajectory",
            )
            ax.plot(trial.error_x_px[0], trial.error_y_px[0], "go", markersize=10, label="Start")
            ax.plot(trial.error_x_px[-1], trial.error_y_px[-1], "ro", markersize=10, label="End")
            ax.plot(0, 0, "k+", markersize=15, markeredgewidth=2, label="Target Center")
            ax.set_title(f"P{trial.position_index}-T{trial.trial_index}", fontsize=10)
            ax.set_xlabel("Error X (px)", fontsize=8)
            ax.set_ylabel("Error Y (px)", fontsize=8)
            ax.axhline(0, color="black", linestyle="--", linewidth=1)
            ax.axvline(0, color="black", linestyle="--", linewidth=1)
            ax.legend(loc="best", fontsize=6)
            ax.grid(True, linestyle=":", alpha=0.7)
            ax.axis("equal")
            ax.tick_params(labelsize=7)

            if trial.position_index == 1:
                ax.text(0.5, 1.24, f"第{trial.trial_index}次", transform=ax.transAxes, ha="center", fontsize=10)
            if trial.trial_index == 1:
                ax.text(-0.34, 0.5, f"位置{trial.position_index}", transform=ax.transAxes, va="center", fontsize=10)

        fig.suptitle("2D Image-Plane Trajectory", fontsize=14, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.98), h_pad=1.4, w_pad=0.9)
        self._save_figure(fig, "fixed_positions_traj_5x5_vector")

    def _save_figure(self, fig, stem: str) -> None:
        """保存 PDF 矢量图，等价于原记录模块将 PNG 输出替换为 PDF。"""
        output_path = self.summary_dir / f"{stem}.pdf"
        fig.savefig(output_path, bbox_inches="tight")
        print(output_path)
        plt.close(fig)


def main() -> None:
    """脚本入口：读取固定位置实验 CSV，生成论文可用的 PDF 矢量汇总图。"""
    builder = VectorSummaryBuilder(RESULTS_DIR, SUMMARY_DIR)
    builder.build()


if __name__ == "__main__":
    main()
