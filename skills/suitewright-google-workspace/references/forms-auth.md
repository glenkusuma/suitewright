# Google Forms authentication

suitewright requests the following OAuth scope for Google Forms:
- `https://www.googleapis.com/auth/forms.body` (read/write access)

## Scope behavior

suitewright requests all required scopes in a single OAuth consent flow. The
complete scope list includes Gmail, Calendar, Drive, Sheets, Docs, Contacts,
and Forms. The SCOPES list is hardcoded in the package — it is not user-configurable.

If you have an existing token from a previous auth flow that does not include
the Forms scope, you must re-authenticate:

```bash
suitewright auth revoke
suitewright auth login
```

This will prompt you to grant consent again, adding the Forms scope to your token.

## Headless authentication

For headless or agent-driven flows, you can split the consent step across machines:

```bash
# Step 1: Generate the OAuth URL
suitewright auth login --auth-url

# Step 2: Visit the URL in a browser, complete consent, then exchange the code
suitewright auth login --auth-code <CODE_OR_REDIRECT_URL>
```

After consent, the redirected localhost URL can be pasted directly as the
`--auth-code` argument.

## Verify auth status

```bash
suitewright auth check
```

Prints `AUTHENTICATED` when the token is valid and includes all required scopes.
