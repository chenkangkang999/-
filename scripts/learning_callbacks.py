"""Opt-in observation callback; imported only by the GPU training entry point."""

from pathlib import Path

from transformers import TrainerCallback


class TrainingObservationCallback(TrainerCallback):
    def save(self, args, state):
        directory = Path(args.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "trainer_state.observed.tmp"
        state.save_to_json(str(temporary))
        temporary.replace(directory / "trainer_state.json")

    def on_train_begin(self, args, state, control, **kwargs):
        self.save(args, state)

    def on_log(self, args, state, control, **kwargs):
        self.save(args, state)

    def on_evaluate(self, args, state, control, **kwargs):
        self.save(args, state)

    def on_train_end(self, args, state, control, **kwargs):
        self.save(args, state)
