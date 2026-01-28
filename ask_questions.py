import subprocess
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser(description="Ask questions using the agent script.")
    parser.add_argument("--model", "-m", required=True, help="The model name to use for generation.")
    parser.add_argument("--provider", "-p", required=True, help="The LLM provider to use (e.g., openai, ollama, google).")
    parser.add_argument("--output-folder", "-o", required=True, help="Folder to save generated answers.")
    parser.add_argument("--input-questions", "-i", required=True, help="Input file containing questions, one per line.")

    args = parser.parse_args()

    output_folder = Path(args.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    input_questions = Path(args.input_questions)
    if not input_questions.exists():
        print(f"Input questions file '{input_questions}' does not exist.")
        return

    # Scan existing answers to skip already processed questions
    existing_answers = {file.stem for file in output_folder.glob("answer_*.txt")}

    with input_questions.open("r") as infile:
        for idx, question in enumerate(infile):
            question = question.strip()
            if not question:
                continue

            output_file = output_folder / f"answer_{idx}.txt"
            if output_file.stem in existing_answers:
                print(f"Skipping question {idx}: '{question}' (already answered)")
                continue

            print(f"Processing question {idx}: '{question}'")

            # Call the agent script via subprocess
            try:
                subprocess.run(
                    [
                        "python", "main.py", "agent",
                        "--provider", args.provider,
                        "--model", args.model,
                        "--topic", question,
                        "--output-folder", str(output_folder),
                        "--output-filename", output_file.name
                    ],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"Error processing question {idx}: {e}")

if __name__ == "__main__":
    main()