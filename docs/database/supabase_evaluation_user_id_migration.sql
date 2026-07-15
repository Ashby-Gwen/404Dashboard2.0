-- Supabase/Postgres migration for evaluation modal support.
-- Adds optional user linkage while preserving existing evaluator name/role fields.

ALTER TABLE public.evaluation_sessions
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id_created
    ON public.evaluation_sessions (user_id, created_at DESC);

-- Optional seed refresh for the revised no-neutral questionnaire.
-- Existing responses remain linked to their original question IDs.
INSERT INTO public.evaluation_questions (display_order, category, question_text, is_active)
SELECT updates.display_order, updates.category, updates.question_text, TRUE
FROM (VALUES
    (1, 'User Experience', 'The system is easy to navigate during regular work tasks.'),
    (2, 'Features', 'The available features support the main sales, invoice, expense, and reporting workflows.'),
    (3, 'Design', 'The interface layout and visual hierarchy make information easy to understand.'),
    (4, 'Compatibility', 'The system works reliably on the devices and browsers used for daily operations.'),
    (5, 'Reliability', 'The system produces consistent results when the same task is repeated.'),
    (6, 'Efficiency', 'The system helps users complete tasks with reasonable time and effort.'),
    (7, 'Security', 'The system provides appropriate access control for each user role.'),
    (8, 'Portability', 'The system can be deployed and maintained across the intended Render and Supabase environment.'),
    (9, 'Overall Agreement', 'Overall, the system is suitable for supporting the organization''s business workflow.')
) AS updates(display_order, category, question_text)
WHERE NOT EXISTS (
    SELECT 1 FROM public.evaluation_questions existing
    WHERE existing.display_order = updates.display_order
);

UPDATE public.evaluation_questions
SET category = updates.category,
    question_text = updates.question_text,
    is_active = TRUE
FROM (VALUES
    (1, 'User Experience', 'The system is easy to navigate during regular work tasks.'),
    (2, 'Features', 'The available features support the main sales, invoice, expense, and reporting workflows.'),
    (3, 'Design', 'The interface layout and visual hierarchy make information easy to understand.'),
    (4, 'Compatibility', 'The system works reliably on the devices and browsers used for daily operations.'),
    (5, 'Reliability', 'The system produces consistent results when the same task is repeated.'),
    (6, 'Efficiency', 'The system helps users complete tasks with reasonable time and effort.'),
    (7, 'Security', 'The system provides appropriate access control for each user role.'),
    (8, 'Portability', 'The system can be deployed and maintained across the intended Render and Supabase environment.'),
    (9, 'Overall Agreement', 'Overall, the system is suitable for supporting the organization''s business workflow.')
) AS updates(display_order, category, question_text)
WHERE public.evaluation_questions.display_order = updates.display_order;

UPDATE public.evaluation_questions
SET is_active = FALSE
WHERE display_order > 9;
