-- Supabase/Postgres migration for Render multi-user persistence hardening.
-- Run this after the user approval migration and before deploying this code.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS profile_photo_data text,
    ADD COLUMN IF NOT EXISTS profile_photo_mime varchar(80);

CREATE TABLE IF NOT EXISTS public.system_settings (
    key varchar(100) PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz DEFAULT now()
);

INSERT INTO public.system_settings (key, value)
VALUES (
    'theme_settings',
    '{"bg":"#F3EFE6","bg_2":"#FFF9ED","orange":"#FF6A00","orange_2":"#FF9F1C","text":"#15130F","muted":"#70695D","glass_opacity":0.58,"glass_strong_opacity":0.72,"glass_border_opacity":0.68,"blur_px":28,"saturate_percent":180,"card_radius_px":8,"control_radius_px":6,"page_padding_px":34,"card_padding_px":24,"stat_padding_px":20,"nav_padding_px":10}'
)
ON CONFLICT (key) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_users_profile_photo_mime ON public.users(profile_photo_mime);
