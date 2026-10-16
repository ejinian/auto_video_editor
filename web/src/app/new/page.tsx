import { NewVideoFlow } from "@/components/new/NewVideoFlow";
import { folderClips, folders, nextDayName, nextProjectName, sounds, validFolderName } from "@/lib/beatcut";

export const dynamic = "force-dynamic";

/** The guided flow: clips (upload or an existing folder) → sound → how to cut. `?folder=dayN` starts at the sound step. */
export default async function NewVideo({ searchParams }: { searchParams: Promise<{ folder?: string }> }) {
  const { folder } = await searchParams;
  const [fs, ss] = await Promise.all([folders(), sounds()]);
  let initial = null;
  if (folder && validFolderName(folder)) {
    const clips = await folderClips(folder);
    if (clips.length) initial = { folder, clips, nextName: nextProjectName(folder) };
  }
  return <NewVideoFlow defaultName={nextDayName()} folders={fs} sounds={ss} initial={initial} />;
}
