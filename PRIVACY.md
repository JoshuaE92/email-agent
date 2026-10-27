# email-agent privacy note

email-agent is a personal tool used only by its owner, Joshua Estime. It is not offered to anyone else.

- It reads the owner's own Gmail with read-only access (gmail.readonly). It cannot send, delete or change email.
- For each recent email, the subject, sender, date and a trimmed copy of the text are sent to Groq's API to find deadlines and to-dos. See Groq's data policy: https://console.groq.com/docs/your-data
- Extracted to-dos (task text, deadline, sender name, Gmail link) are stored in a private GitHub repository and sent to the owner's phone through ntfy.sh.
- No data is sold, shared or used for advertising.
- To revoke access at any time, go to https://myaccount.google.com/permissions and remove "email-agent".

Contact: josh.n.estime@gmail.com
