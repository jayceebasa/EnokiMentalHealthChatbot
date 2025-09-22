import os
import requests

# ------------------ Config ------------------
API_URL = os.getenv("API_URL", "http://127.0.0.1:8001")
VERBOSE = os.getenv("VERBOSE", "true").lower() in {"1", "true", "yes", "on"}

# ------------------ Test Sentences ------------------
sentences = [
    "Oh great, I spilled coffee all over my shirt this morning while rushing to my meeting!",
    "I finally finished my project ahead of time, and my boss seemed genuinely impressed.",
    "Wonderful, my train was delayed again, making me late for an important appointment!",
    "I had a healthy breakfast today, feeling energized for the rest of the morning.",
    "Fantastic, I got stuck in traffic for two hours and missed my friend's birthday dinner.",
    "I read a book in the afternoon and really enjoyed the plot twists.",
    "Oh joy, my laptop crashed mid-assignment, losing all my unsaved work.",
    "I took my dog for a walk today, enjoying the fresh air and sunshine.",
    "Amazing, my phone battery died mid-call when I was explaining my project!",
    "I watered the plants today and they look much healthier now.",
    "Best day ever, lost my wallet on the way to work and had to cancel all my cards!",
    "I cooked dinner for my family, and everyone loved it.",
    "Thrilled beyond words that my flight got cancelled, ruining my weekend plans.",
    "I went grocery shopping today and found everything on my list.",
    "Absolutely perfect, spilled tea on my notes right before the presentation.",
    "I did some laundry, and finally organized my clothes.",
    "So amazing, the printer ran out of ink right as I was printing my assignment.",
    "I had a short nap in the afternoon and feel more refreshed now.",
    "My cat knocked over my vase, wonderful! It shattered everywhere.",
    "I called my friend today to catch up and had a great conversation.",
    "Couldn't be happier, missed my bus this morning and was late for work.",
    "I watered the garden today and the flowers are blooming beautifully.",
    "Just what I needed, a flat tire on the way to work during rush hour.",
    "I listened to some music while relaxing, and it lifted my mood.",
    "My favorite show got cancelled, amazing! I was looking forward to it all week.",
    "I did a 30-minute workout and feel proud of sticking to my routine.",
    "So grateful, lost all my files due to a crash right before the deadline.",
    "I cleaned my desk today and finally feel organized.",
    "Absolutely amazing, got a parking ticket while running a quick errand.",
    "I took a relaxing shower and feel refreshed and calm.",
    "Living the dream, my phone stopped working mid-call when I was talking to my parents!",
    "I had a nice chat with a colleague and exchanged some helpful tips.",
    "Best day ever, my coffee spilled on the keyboard right before submitting my report.",
    "I cooked a new recipe and it turned out delicious!",
    "Truly blessed, forgot my wallet at home and had to borrow money from a friend.",
    "I watered my indoor plants and they are thriving.",
    "So wonderful, printer jammed again in the middle of printing my tickets.",
    "I went for a walk in the park and enjoyed the fresh air and scenery.",
    "My alarm didn't go off, fantastic! I was late for my meeting.",
    "I wrote in my journal today and reflected on my achievements.",
    "Absolutely perfect, my email got lost right before the client meeting.",
    "I organized my bookshelf and found books I forgot I had.",
    "Wonderful, my package was delivered to the wrong address, again.",
    "I meditated for 15 minutes and feel more centered and calm.",
    "Just what I needed, my car wouldn't start when I was running late.",
    "I called my parents to check on them and had a lovely chat.",
    "So amazing, the internet went down during my online presentation.",
    "I practiced piano today and managed to play the difficult parts flawlessly.",
    "Thrilled beyond words, spilled juice on my notes just before submitting them.",
    "I did a puzzle and enjoyed solving it piece by piece.",

]

# 1 = sarcastic, 0 = not sarcastic
GROUND_TRUTH = [
    1,0,1,0,1,0,1,0,1,0,
    1,0,1,0,1,0,1,0,1,0,
    1,0,1,0,1,0,1,0,1,0,
    1,0,1,0,1,0,1,0,1,0,
    1,0,1,0,1,0,1,0,1,0
]

assert len(sentences) == len(GROUND_TRUTH), "Ground truth length mismatch"

# ------------------ Fetch API thresholds ------------------
health = requests.get(f"{API_URL}/").json()
STRICT_THR = float(health.get("strict_threshold", 0.55))
POSSIBLE_THR = float(health.get("possible_threshold", 0.25))

# ------------------ Evaluation Metrics ------------------
strict_correct = 0
inclusive_correct = 0

true_pos = false_pos = true_neg = false_neg = 0

# ------------------ Run Tests ------------------
for idx, (text, truth) in enumerate(zip(sentences, GROUND_TRUTH), start=1):
    try:
        resp = requests.post(f"{API_URL}/predict_all", json={"text": text}).json()
        label = resp.get("sarcasm", "not_sarcastic")
        score = resp.get("sarcasm_score", 0.0)

        # Strict: only 'sarcastic' counts as positive
        strict_pred_positive = label == "sarcastic"
        # Inclusive: 'sarcastic' or 'possibly_sarcastic' counts as positive
        inclusive_pred_positive = label in {"sarcastic", "possibly_sarcastic"}

        # Accuracy counts
        if (strict_pred_positive and truth == 1) or (not strict_pred_positive and truth == 0):
            strict_correct += 1
        if (inclusive_pred_positive and truth == 1) or (not inclusive_pred_positive and truth == 0):
            inclusive_correct += 1

        # Confusion matrix (inclusive)
        if inclusive_pred_positive and truth == 1:
            true_pos += 1
            outcome = "TP"
        elif inclusive_pred_positive and truth == 0:
            false_pos += 1
            outcome = "FP"
        elif not inclusive_pred_positive and truth == 0:
            true_neg += 1
            outcome = "TN"
        else:
            false_neg += 1
            outcome = "FN"

        if VERBOSE:
            gt_label = "sarcastic" if truth == 1 else "not_sarcastic"
            print(f"[{idx:02d}] {outcome} GT={gt_label:<11} Pred={label:<18} Score={score:.2f} Text={text}")

    except Exception as e:
        print(f"[{idx:02d}] ERROR calling API: {e}")

# ------------------ Metrics Calculation ------------------
n = len(sentences)
strict_acc = strict_correct / n
inclusive_acc = inclusive_correct / n
precision = true_pos / (true_pos + false_pos) if (true_pos + false_pos) else 0.0
recall = true_pos / (true_pos + false_neg) if (true_pos + false_neg) else 0.0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

# ------------------ Summary ------------------
print("\n=== Sarcasm Evaluation Summary ===")
print(f"Total Sentences: {n}")
print(f"Strict Accuracy:    {strict_acc:.2%}")
print(f"Inclusive Accuracy: {inclusive_acc:.2%}")
print(f"Precision: {precision:.2%}  Recall: {recall:.2%}  F1: {f1:.2%}")
print(f"Confusion (Inclusive): TP={true_pos} FP={false_pos} TN={true_neg} FN={false_neg}")
print(f"Thresholds (strict/possible): {STRICT_THR}/{POSSIBLE_THR}")
print(f"\nFinal Score (Inclusive): {inclusive_correct}/{n} correct")
print(f"Final Score (Strict):    {strict_correct}/{n} correct")
print("Done.")
