"use client";

import { useCallback, useState } from "react";
import { ClipsStep, type FolderClips } from "@/components/new/ClipsStep";
import { CutStep } from "@/components/new/CutStep";
import { SoundStep } from "@/components/new/SoundStep";
import type { ClipInfo, FolderInfo, SoundInfo } from "@/lib/types";

const STEPS = ["Clips", "Sound", "Cut"];

export function NewVideoFlow({ defaultName, folders, sounds: initialSounds, initial }: {
  defaultName: string;
  folders: FolderInfo[];
  sounds: SoundInfo[];
  initial: FolderClips | null;
}) {
  const [step, setStep] = useState(initial ? 2 : 1);
  const [folder, setFolder] = useState<string | null>(initial?.folder ?? null);
  const [clips, setClips] = useState<ClipInfo[]>(initial?.clips ?? []);
  const [nextName, setNextName] = useState(initial?.nextName ?? "");
  const [sounds, setSounds] = useState(initialSounds);
  const [sound, setSound] = useState<string | null>(null);
  const onFolder = useCallback((f: FolderClips) => { setFolder(f.folder); setClips(f.clips); setNextName(f.nextName); }, []);
  const selected = sounds.find((s) => s.path === sound) ?? null;
  const can = [true, clips.length > 0 && !!folder, !!selected && clips.length > 0];
  const sub = [
    folder ? `${folder} · ${clips.length} clips` : "name a folder, drop the clips",
    selected ? selected.title : "pick one from the pool or paste a link",
    "length, pace, opener, order",
  ];

  return (
    <div>
      <h1>New video</h1>
      <p className="lede">Three steps to a finished mp4: the clips, the sound, how to cut it. About two minutes.</p>
      <div className="steps">
        {STEPS.map((label, i) => {
          const n = i + 1;
          return (
            <button key={label} type="button" className={n === step ? "on" : n < step ? "done" : ""} disabled={!can[i] || n === step} onClick={() => setStep(n)}>
              <span className="k">{n < step ? "✓" : n}</span>
              <span className="min-w-0"><span className="t">{label}</span><span className="s">{sub[i]}</span></span>
            </button>
          );
        })}
      </div>

      {step === 1 && <ClipsStep defaultName={defaultName} folders={folders} folder={folder} clips={clips} onFolder={onFolder} onNext={() => setStep(2)} />}
      {step === 2 && folder && (
        <SoundStep folder={folder} clipCount={clips.length} sounds={sounds} selected={sound} onSounds={setSounds} onSelect={setSound} onBack={() => setStep(1)} onNext={() => setStep(3)} />
      )}
      {step === 3 && folder && selected && <CutStep folder={folder} clips={clips} sound={selected} nextName={nextName} onBack={() => setStep(2)} />}
    </div>
  );
}
