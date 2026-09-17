# OMNIX production auth gate

The application already uses Supabase Auth as its authentication authority. The production gate must validate the Supabase session before rendering the protected dashboard. Backend/API reachability is an application-data concern and must not determine whether a valid Supabase session exists.

Protected application UI remains inside the existing `AuthContainer`; no duplicate auth provider or duplicate dashboard implementation is introduced.
