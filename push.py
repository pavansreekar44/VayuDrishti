import os

print("Staging all files...")
os.system('git add .')

print("Committing fixes (Batch Size, Architecture, OOM patches)...")
os.system('git commit -m "Fix PyTorch OOM limits, reduce A3TGCN batch size, and finalize dashboard logic for India Innovates"')

print("Pushing to GitHub remote...")
exit_code = os.system('git push origin main')

if exit_code == 0:
    print("\nSUCCESS! Code pushed to GitHub. You can now use !git pull in Colab!")
else:
    print("\nERROR: Push failed. Make sure you are authenticated with GitHub.")
