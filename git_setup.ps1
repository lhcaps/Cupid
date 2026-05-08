git config --global --add safe.directory E:/Macro/Cupid
git config --global user.email "lhcaps@example.com"
git config --global user.name "lhcaps"
git add -A
git commit -m "Initial commit: VisionCombatLab structure

- Refactor to match VisionFlow project structure
- docs/: README, DESIGN
- .planning/: ROADMAP, PROJECT, spikes
- Root: README, PROJECT, pyproject
- .github/workflows/ci.yml
- .gitignore"
git branch -M main
git remote add origin https://github.com/lhcaps/Cupid.git
git push -u origin main
