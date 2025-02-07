import pandas as pd
import matplotlib.pyplot as plt


class MetricsVisualizer:
    def __init__(
        self,
        csv_file_path="metrics.csv",
        image_file_path="metrics.png",
        time_field="time",
        label_field="velocity",
        prediction_field="velocity_pred",
        error_field="mae",
        max_xticks=40,
    ):
        self.csv_file_path = csv_file_path
        self.image_file_path = image_file_path
        self.time_field = time_field
        self.label_field = label_field
        self.error_field = error_field
        self.prediction_field = prediction_field
        self.max_xticks = max_xticks

    def plot_metrics(self):
        df = pd.read_csv(self.csv_file_path)
        if self.time_field not in df.columns:
            raise ValueError(f"Time field '{self.time_field}' not found.")
        if self.label_field not in df.columns:
            raise ValueError(f"Label field '{self.label_field}' not found.")
        if self.prediction_field not in df.columns:
            raise ValueError(f"Prediction field '{self.prediction_field}' not found.")
        df["hms"] = pd.to_datetime(df["time"], unit="s").dt.strftime("%H:%M:%S")
        _, ax = plt.subplots()
        ax.set_xticks(range(0, len(df), 40))
        ax.plot(df["hms"], df[self.label_field], color=(0.8, 0.8, 0.8), label="actual")
        ax.plot(
            df["hms"],
            df[self.prediction_field],
            linestyle="dashed",
            color=(0.2, 0.2, 0.2),
            label="predicted",
        )
        ax.plot(
            df["hms"],
            df[self.error_field],
            color=(0.3, 0.3, 0.3),
            label="error",
        )
        ax.legend()
        plt.savefig(self.image_file_path)


metrics_visualizer = MetricsVisualizer()
metrics_visualizer.plot_metrics()
