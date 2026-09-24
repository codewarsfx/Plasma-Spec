"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, User } from "lucide-react";

import { getProfile, updateProfile, uploadAvatar } from "@/lib/api";
import { toast } from "@/components/Toast";
import type { Profile } from "@/lib/types";

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getProfile()
      .then((data) => {
        setProfile(data);
        setDisplayName(data.display_name ?? "");
      })
      .catch((exc) => toast.error("Couldn't load profile", exc instanceof Error ? exc.message : "unknown error"))
      .finally(() => setLoading(false));
  }, []);

  async function saveDisplayName() {
    setSaving(true);
    try {
      const updated = await updateProfile(displayName.trim() || null);
      setProfile(updated);
      toast.success("Profile updated");
    } catch (exc) {
      toast.error("Couldn't save", exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setSaving(false);
    }
  }

  async function handleAvatarChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setAvatarBusy(true);
    try {
      const updated = await uploadAvatar(file);
      setProfile(updated);
      toast.success("Avatar updated");
    } catch (exc) {
      toast.error("Upload failed", exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setAvatarBusy(false);
      event.target.value = "";
    }
  }

  if (loading) {
    return <div className="mx-auto max-w-lg px-4 py-16 text-center text-sm text-slate-500">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <h1 className="text-xl font-semibold text-ink">Your profile</h1>
      <p className="mt-1 text-sm text-slate-500">
        Your display name and avatar show up next to anything you share to the activity feed.
      </p>

      <div className="mt-6 flex items-center gap-4">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={avatarBusy}
          className="relative flex h-16 w-16 items-center justify-center overflow-hidden border border-line bg-slate-50 text-slate-400"
          style={{ borderRadius: 999 }}
          title="Change avatar"
        >
          {avatarBusy ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : profile?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={profile.avatar_url} alt="" className="h-full w-full object-cover" />
          ) : (
            <User className="h-7 w-7" />
          )}
        </button>
        <div>
          <button type="button" className="text-button" onClick={() => fileInputRef.current?.click()} disabled={avatarBusy}>
            Change avatar
          </button>
          <p className="mt-1 text-xs text-slate-500">PNG/JPEG/WebP, up to 2MB.</p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleAvatarChange}
        />
      </div>

      <label className="mt-6 grid gap-1">
        <span className="control-label">Display name</span>
        <input
          className="field"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="How you'll appear to other members"
        />
      </label>

      <label className="mt-4 grid gap-1">
        <span className="control-label">Email</span>
        <input className="field" value={profile?.email ?? "(local account)"} disabled />
      </label>

      <button
        type="button"
        className="primary-button mt-6"
        onClick={saveDisplayName}
        disabled={saving}
      >
        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Save changes
      </button>
    </div>
  );
}
