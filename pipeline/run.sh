#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/runs/lysozyme}"
mkdir -p "$OUT"
cd "$OUT"

gmx pdb2gmx -f "$HERE/1AKI.pdb" -o conf.gro -p topol.top -ff amber99sb-ildn -water tip3p
gmx editconf -f conf.gro -o box.gro -c -d 1.0 -bt cubic
gmx solvate -cp box.gro -cs spc216.gro -o solv.gro -p topol.top
gmx grompp -f "$HERE/minim.mdp" -c solv.gro -p topol.top -o em.tpr -maxwarn 2
gmx mdrun -deffnm em -nb cpu
gmx grompp -f "$HERE/nvt.mdp" -c em.gro -p topol.top -o nvt.tpr -maxwarn 2
gmx mdrun -deffnm nvt -nb cpu -notunepme

printf "12\n0\n" | gmx energy -f nvt.edr -o energy.xvg

cp nvt.xtc traj.xtc
cp nvt.tpr topol.tpr
cp nvt.gro conf.gro

rm -f box.gro solv.gro em.gro em.edr em.log em.tpr em.trr nvt.gro nvt.edr nvt.cpt nvt.trr nvt.log mdout.mdp posre.itp state.cpt
echo "canonical run-dir ready at: $OUT"
ls -la "$OUT"
