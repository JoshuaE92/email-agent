"""Source for eval/dataset.json (40 synthetic emails + hand-written labels).

Edit the list below, then run:  python eval/build_dataset.py
All companies and people are made up.

Labeling rules (the same rules the prompt gives the model):
  * deadline  = the earliest date Josh must DO something (reply, submit, pay),
                or the date of the event/interview/appointment if there's
                nothing to do before it. Overdue items keep their past date.
  * urgency   = high if deadline <= sent date + 2 days (or overdue),
                medium if <= 7 days, low otherwise or no deadline.
  * "today" in the eval = the email's sent date, so relative dates
    ("by Friday") have one correct answer.
"""
import json
import os

UNSUB = {"List-Unsubscribe": "<mailto:unsubscribe@list.example.com>"}


def E(id, tags, subject, sender, date, body, actionable, deadline, urgency, category,
      headers=None, notes=""):
    return {"id": id, "tags": tags, "notes": notes,
            "email": {"subject": subject, "sender": sender, "date": date,
                      "headers": headers or {}, "body": body.strip()},
            "expected": {"is_actionable": actionable, "deadline": deadline,
                         "urgency": urgency, "category": category}}


DATA = [
    # ---------------- career ----------------
    E("interview_confirm_by", ["interview", "two_dates"],
      "Interview invitation – Software Engineering Intern (Summer 2027)",
      "Priya Shah <pshah@brightlinecap.com>", "2026-10-19T10:04:00-04:00", """
Hi Joshua,

Thank you for completing the technical screen. We'd like to invite you to a virtual
final-round interview on Thursday, October 29 at 2:00 PM ET (three 45-minute sessions).

Please confirm your availability by replying to this email by Wednesday, October 21.
If that time doesn't work, let me know a few alternatives.

Best,
Priya Shah
University Recruiting, Brightline Capital""",
      True, "2026-10-21", "high", "career",
      notes="Two dates: the reply deadline (Oct 21) comes first."),

    E("interview_scheduled_ats", ["interview", "noreply_ats"],
      "Your interview with Tessera Labs is confirmed",
      "Tessera Labs Recruiting <no-reply@greenhouse-mail.example.com>", "2026-10-22T16:30:00-04:00", """
Hi Joshua,

Your interview has been scheduled.

Position: Backend Engineer Intern
Date: Tuesday, November 3, 2026
Time: 11:00 AM – 12:00 PM Eastern
Location: Zoom (link below)

https://zoom.example.com/j/88812345

Need to reschedule? Use the link in this email at least 24 hours in advance.""",
      True, "2026-11-03", "low", "career", headers=UNSUB),

    E("oa_relative_7_days", ["oa", "relative_date"],
      "Complete your Online Assessment for Northwind Robotics",
      "HackerRank <noreply@hackerrank-mail.example.com>", "2026-10-23T09:12:00-04:00", """
Hello Joshua,

Northwind Robotics has invited you to complete an online coding assessment for the
Software Engineer Intern role.

Duration: 90 minutes
You have 7 days from receipt of this email to complete the assessment.

Start assessment: https://hr.example.com/test/abc123

Good luck!""",
      True, "2026-10-30", "medium", "career", headers=UNSUB),

    E("oa_expires_date", ["oa"],
      "Halcyon Systems invited you to take a General Coding Assessment",
      "CodeSignal <no-reply@codesignal-mail.example.com>", "2026-10-26T08:15:00-04:00", """
Hi Joshua,

Halcyon Systems would like you to take the General Coding Assessment (GCA).
This invitation expires on 11/02/2026 at 11:59 PM PT.

Take the assessment: https://app.example.com/gca/xyz

Make sure you have a stable internet connection and a quiet place.""",
      True, "2026-11-02", "medium", "career", headers=UNSUB),

    E("onboarding_list_buried", ["onboarding", "buried_deadline"],
      "Welcome to Ridgeview Aerospace – pre-start checklist",
      "Ridgeview Onboarding <onboarding@ridgeview-aero.example.com>", "2026-10-20T11:00:00-04:00", """
Hi Joshua,

Welcome aboard! We're thrilled you'll be joining the Ridgeview Aerospace internship
program in January. Your manager, Dana Kim, will reach out closer to your start date.

Here's what to expect over the next few weeks. Our team will send your laptop about a
week before you start, and you'll receive your badge on day one at the Orlando site.
Parking is free in Lot C.

Before your start date, please complete the following in the onboarding portal:
  1. Form I-9 Section 1 — due by October 30.
  2. Direct deposit setup — any time before your first paycheck.
  3. Benefits enrollment — opens on your start date.

If you have questions, just reply to this email.

Ridgeview People Team""",
      True, "2026-10-30", "low", "career"),

    E("onboarding_reminder", ["onboarding", "reminder"],
      "Reminder: Form I-9 Section 1 still incomplete",
      "Ridgeview Onboarding <onboarding@ridgeview-aero.example.com>", "2026-10-27T09:00:00-04:00", """
Hi Joshua,

This is a friendly reminder that your Form I-9 Section 1 is still incomplete in the
onboarding portal. It is due in 3 days (October 30). Federal law requires it to be
completed before your start date.

Complete it here: https://portal.example.com/onboarding

Thanks,
Ridgeview People Team""",
      True, "2026-10-30", "medium", "career",
      notes="Repeat of onboarding_list_buried; the extractor should still flag it, dedup suppresses it."),

    E("background_check_72h", ["background_check", "relative_date"],
      "Ridgeview Aerospace has requested a background check",
      "Verifi Screening <noreply@verifi-screening.example.com>", "2026-10-21T13:20:00-04:00", """
Hi Joshua,

Ridgeview Aerospace has asked Verifi to run a background check as part of your offer.
Please provide your information and consent within 72 hours so there are no delays.

Start here: https://candidate.example.com/invite/7f3a9

This link is unique to you. Do not share it.""",
      True, "2026-10-24", "medium", "career", headers=UNSUB),

    E("background_check_reminder", ["background_check", "reminder", "relative_date"],
      "Reminder: your background check is waiting",
      "Verifi Screening <noreply@verifi-screening.example.com>", "2026-10-23T09:00:00-04:00", """
Hi Joshua,

We still need your information to start the background check requested by
Ridgeview Aerospace. Your invitation will expire tomorrow.

Continue: https://candidate.example.com/invite/7f3a9""",
      True, "2026-10-24", "high", "career", headers=UNSUB),

    E("rejection_plain", ["rejection"],
      "Update on your application",
      "Tessera Labs Careers <careers@tessera-labs.example.com>", "2026-10-21T17:45:00-04:00", """
Dear Joshua,

Thank you for your interest in the Data Engineering Intern position at Tessera Labs.
After careful review, we have decided to move forward with other candidates whose
experience more closely matches our needs at this time.

We'll keep your resume on file and encourage you to apply to future openings.

Best regards,
Tessera Labs Talent Team""",
      False, None, "low", "career"),

    E("rejection_mentions_past_date", ["rejection", "past_date"],
      "Your application status – Quant Developer Intern",
      "Brightline Capital <recruiting@brightlinecap.com>", "2026-10-24T12:10:00-04:00", """
Hi Joshua,

Thank you for taking the time to interview with us on October 14. The team enjoyed
meeting you. Unfortunately, we will not be moving forward with your candidacy for the
Quant Developer Intern role.

We wish you the best in your search.""",
      False, None, "low", "career"),

    E("offer_expires_relative", ["offer", "relative_date"],
      "Your offer from Halcyon Systems",
      "Morgan Reyes <mreyes@halcyon-systems.example.com>", "2026-10-22T15:00:00-04:00", """
Hi Joshua,

Congratulations! We're excited to extend you an offer for the Software Engineering
Intern position for Summer 2027. Please review and sign your offer letter in Workday.

This offer expires in two weeks. Let me know if you have any questions or want to
talk through the details.

Morgan""",
      True, "2026-11-05", "low", "career"),

    E("recruiter_waiting_no_date", ["reply_waiting"],
      "Great chatting yesterday",
      "Marcus Lee <mlee@northwind-robotics.example.com>", "2026-10-23T10:30:00-04:00", """
Hi Joshua,

Thanks for stopping by our booth at the career fair yesterday! I'd like to set up a
quick call with our hiring manager. Could you send over your availability for next
week and an updated copy of your resume?

Thanks,
Marcus""",
      True, None, "low", "career",
      notes="Someone is waiting on a reply but gave no date."),

    # ---------------- bills ----------------
    E("utility_bill_due", ["bill"],
      "Your Orlando Power & Water statement is ready",
      "OPW Billing <noreply@opw-billing.example.com>", "2026-10-22T06:00:00-04:00", """
Your statement for account ending in 4471 is ready.

Statement date: October 22, 2026
Amount due: $84.12
Due date: November 9, 2026

AutoPay is not enabled on this account. Pay online at https://pay.example.com""",
      True, "2026-11-09", "low", "bills", headers=UNSUB),

    E("autopay_scheduled", ["bill", "no_action_needed"],
      "Your AutoPay payment is scheduled",
      "Lumen Mobile <billing@lumen-mobile.example.com>", "2026-10-25T07:00:00-04:00", """
Hi Joshua,

Your AutoPay payment of $45.00 will be drafted from your checking account on
November 1. No action is needed.

Thanks for being a Lumen Mobile customer.""",
      False, None, "low", "bills",
      notes="Bill with a date but nothing to do."),

    E("credit_card_due_soon", ["bill"],
      "Payment due soon",
      "Summit Card Services <alerts@summitcard.example.com>", "2026-10-26T07:30:00-04:00", """
Your minimum payment of $35.00 is due on 10/28/2026.

Statement balance: $412.55
Pay now: https://summitcard.example.com/pay

If you've already paid, thank you, you can ignore this message.""",
      True, "2026-10-28", "high", "bills"),

    E("phone_bill_past_due", ["bill", "past_date", "overdue"],
      "Your account is past due",
      "Lumen Mobile <billing@lumen-mobile.example.com>", "2026-10-24T08:00:00-04:00", """
Hi Joshua,

Your payment of $62.40 was due on October 20 and we haven't received it yet.
Please pay now to avoid a late fee and service interruption.

Pay: https://lumen-mobile.example.com/pay""",
      True, "2026-10-20", "high", "bills",
      notes="Overdue: deadline is in the past but it still needs action."),

    E("refund_issued", ["bill", "no_action_needed"],
      "Refund issued for duplicate charge",
      "Summit Card Services <alerts@summitcard.example.com>", "2026-10-23T14:00:00-04:00", """
Good news. We've issued a refund of $18.99 for the duplicate charge from
CAMPUS BOOKSTORE on 10/18. It should appear on your statement within 3-5 business days.
No further action is required.""",
      False, None, "low", "bills"),

    # ---------------- school ----------------
    E("canvas_assignment", ["class_assignment"],
      "Assignment Due: COP 4331 – Project Milestone 2",
      "Canvas Notifications <notifications@instructure.example.com>", "2026-10-23T12:00:00-04:00", """
COP 4331C - Processes for Object-Oriented Software Development

Project Milestone 2 has been posted.
Due: Nov 2 at 11:59pm

Submit your group's design document and API spec through Canvas.""",
      True, "2026-11-02", "low", "school"),

    E("prof_by_friday", ["class_assignment", "relative_date"],
      "PS6 writeup reminder",
      "Dr. Elena Park <epark@ucf.edu>", "2026-10-26T09:40:00-04:00", """
Hi all,

Quick reminder that the problem set 6 writeup is due by Friday at 5pm. Late
submissions lose 10% per day. Office hours this week are Wednesday 2-4pm.

- Dr. Park""",
      True, "2026-10-30", "medium", "school"),

    E("ta_buried_regrade", ["class_assignment", "buried_deadline", "relative_date"],
      "Lab 7 notes + a few announcements",
      "Kevin Tran (TA) <kevin.tran@ucf.edu>", "2026-10-22T20:15:00-04:00", """
Hey everyone,

Thanks for a great lab today. A few notes on Lab 7: most groups got the linked-list
reversal working, but a lot of submissions still leak memory in the delete function.
Run valgrind before you submit. I've posted a sample solution for Lab 6 under Files.

Grading for Lab 6 is finished. The average was 86 and the most common deduction was
missing comments. Please include a header comment with your name and NID.

Oh, and one more thing: regrade requests for Exam 2 must be submitted through
Webcourses by Tuesday, otherwise grades are final.

Next week we'll cover hash tables, so skim chapter 11 if you can. Office hours are
moving to Thursday 3-5pm in HEC 308 for the rest of the semester.

Kevin""",
      True, "2026-10-27", "medium", "school",
      notes="Deadline buried in paragraph 3; 'Tuesday' from Thu Oct 22 = Oct 27."),

    E("grades_posted_fyi", ["fyi"],
      "Exam 2 grades are posted",
      "Canvas Notifications <notifications@instructure.example.com>", "2026-10-21T18:00:00-04:00", """
COT 3100 - Introduction to Discrete Structures

Grades for Exam 2 have been posted. Log in to Canvas to view your score and feedback.""",
      False, None, "low", "school"),

    E("financial_aid_documents", ["form"],
      "Verification documents needed",
      "UCF Financial Aid <finaid@ucf.edu>", "2026-10-19T10:00:00-04:00", """
Dear Joshua,

Your 2027-28 FAFSA has been selected for verification. We need additional documents
to complete your file. Please upload your signed verification worksheet through myUCF
by November 15, 2026. Your aid cannot be disbursed until verification is complete.

UCF Office of Student Financial Assistance""",
      True, "2026-11-15", "low", "school"),

    E("registrar_closure_fyi", ["fyi", "has_date"],
      "Offices closed November 11",
      "UCF Registrar <registrar@ucf.edu>", "2026-10-26T11:00:00-04:00", """
All Registrar's Office locations will be closed on Wednesday, November 11 in
observance of Veterans Day. Online services remain available.""",
      False, None, "low", "school"),

    E("dept_newsletter", ["newsletter", "has_date"],
      "CS Department Newsletter – October",
      "UCF Computer Science <cs-news@cs.ucf.edu>", "2026-10-20T08:00:00-04:00", """
In this issue:
- Faculty spotlight: Dr. Ramirez's lab wins NSF grant
- Student org highlights: the Robotics Club placed 2nd at regionals
- Upcoming: guest lecture on quantum computing (Nov 4), Fall hackathon (Nov 14)
- Alumni news and job board

Read the full newsletter on our website.""",
      False, None, "low", "school", headers=UNSUB,
      notes="Newsletter that mentions future dates but asks nothing."),

    E("group_member_waiting", ["reply_waiting", "relative_date"],
      "API endpoints?",
      "Ana Gomez <ana.gomez.dev@gmail.com>", "2026-10-26T13:05:00-04:00", """
Hey Josh,

Are you still able to do the API endpoints for the group project? I need to know by
tonight so I can plan the frontend this week. Let me know either way!

Ana""",
      True, "2026-10-26", "high", "school"),

    E("thread_already_done", ["reply", "past_date", "quoted_history"],
      "Re: Internship credit form",
      "Career Services <careerservices@ucf.edu>", "2026-10-22T09:30:00-04:00", """
Hi Joshua,

Got it, thank you! Your internship credit form is complete and has been sent to your
advisor. You're all set.

Career Services

On Mon, Oct 12, 2026 at 9:00 AM Career Services <careerservices@ucf.edu> wrote:
> Please submit your internship credit form by October 20 so we can process it.""",
      False, None, "low", "school",
      notes="Old request in the quoted history is already done."),

    # ---------------- appointments ----------------
    E("dentist_confirmation", ["appointment"],
      "Appointment confirmed: Dental cleaning",
      "Bright Smiles Dental <appointments@brightsmiles.example.com>", "2026-10-20T15:00:00-04:00", """
Hi Joshua,

Your appointment is scheduled for Tuesday, October 27 at 3:30 PM with Dr. Patel.
Address: 1200 University Blvd, Suite 4.

Reply C to confirm or call us to reschedule.""",
      True, "2026-10-27", "medium", "appointments"),

    E("health_appt_tomorrow", ["appointment", "relative_date"],
      "Reminder: your appointment is tomorrow",
      "UCF Student Health <noreply@health.ucf.edu>", "2026-10-26T12:00:00-04:00", """
This is a reminder of your appointment on Tuesday, October 27 at 10:00 AM at the
Student Health Center. Please arrive 10 minutes early and bring your student ID.""",
      True, "2026-10-27", "high", "appointments"),

    E("service_completed", ["appointment", "no_action_needed"],
      "Thanks for visiting Precision Auto Care",
      "Precision Auto Care <noreply@precisionauto.example.com>", "2026-10-24T16:00:00-04:00", """
Thank you for visiting Precision Auto Care today. Your oil change is complete and your
next service is recommended in 5,000 miles. We'd love to hear about your visit!""",
      False, None, "low", "appointments", headers=UNSUB),

    # ---------------- events ----------------
    E("tech_talk_rsvp", ["event", "two_dates"],
      "ACM Tech Talk with Northwind Robotics – RSVP",
      "UCF ACM <acm@ucf.edu>", "2026-10-21T10:00:00-04:00", """
Hi Knights!

Join us Thursday, November 5 at 6 PM in HEC 101 for a tech talk with engineers from
Northwind Robotics, followed by resume reviews. Please RSVP by Monday, November 2 so
we can order enough food.

RSVP: https://forms.example.com/acm-nw""",
      True, "2026-11-02", "low", "events",
      notes="RSVP deadline (Nov 2) comes before the event (Nov 5)."),

    E("calendar_invite_friend", ["event"],
      "Invitation: Friendsgiving potluck @ Sat Nov 21, 2026 6pm - 10pm (EST)",
      "Jordan Blake <jordan.blake.92@gmail.com>", "2026-10-26T19:00:00-04:00", """
Jordan Blake has invited you to an event.

Friendsgiving potluck
When: Saturday, November 21, 2026, 6pm – 10pm Eastern Time
Where: Jordan's apartment
Bring a dish! Reply Yes / No / Maybe.""",
      True, "2026-11-21", "low", "events"),

    E("club_gbm_this_wednesday", ["event", "relative_date", "filter_risk"],
      "GBM this Wednesday!",
      "UCF Robotics Club <robotics@knights.example.com>", "2026-10-26T10:00:00-04:00", """
Hey everyone,

Our general body meeting is this Wednesday at 7pm in the Student Union, room 218.
We'll announce the competition teams and there will be pizza.

See you there!""",
      True, "2026-10-28", "high", "events", headers=UNSUB,
      notes="Mailing-list email with no rescue keyword: the cheap filter may drop it."),

    E("career_fair_thanks", ["event", "past_date"],
      "Thanks for attending the Fall Career Expo!",
      "UCF Career Services <careerservices@ucf.edu>", "2026-10-22T09:00:00-04:00", """
Thanks for attending the Fall Career Expo on October 20! Over 150 employers attended.
Slides from the employer panel are attached. We hope to see you at the Spring Expo.""",
      False, None, "low", "events"),

    # ---------------- personal / other ----------------
    E("mom_call_saturday", ["personal", "relative_date"],
      "grandma's birthday",
      "Mom <estime.family.mom@gmail.com>", "2026-10-21T20:00:00-04:00", """
Hi baby, don't forget to call grandma for her birthday this Saturday. She'd love to
hear from you. Love you!""",
      True, "2026-10-24", "medium", "personal"),

    E("lease_renewal", ["form", "relative_date"],
      "Lease renewal decision needed",
      "The Pointe Apartments <leasing@thepointe.example.com>", "2026-10-19T12:00:00-04:00", """
Hi Joshua,

Your current lease ends on December 31. Please let us know whether you intend to
renew by the 31st of this month so we can prepare your paperwork. Renewal rates are
attached.

The Pointe Leasing Office""",
      True, "2026-10-31", "low", "personal"),

    E("security_alert_fyi", ["fyi", "noreply"],
      "New sign-in on Mac",
      "Accounts <no-reply@accounts.example.com>", "2026-10-25T22:10:00-04:00", """
We noticed a new sign-in to your account on a Mac device.
If this was you, you don't need to do anything. If not, we'll help you secure your
account.""",
      False, None, "low", "other"),

    E("tech_newsletter", ["newsletter"],
      "The Weekly Byte: AI agents, Rust 2.0 and more",
      "The Weekly Byte <newsletter@weeklybyte.example.com>", "2026-10-25T07:00:00-04:00", """
This week's top stories:
1. Why every startup is building AI agents
2. Rust 2.0 roadmap announced
3. 10 VS Code extensions you need

Read more on our site. You're receiving this because you subscribed.""",
      False, None, "low", "other", headers=UNSUB),

    E("receipt_dining", ["receipt"],
      "Your receipt from Knight Bites",
      "Knight Bites <receipts@knightbites.example.com>", "2026-10-24T13:00:00-04:00", """
Thanks for your order!
Chicken bowl ........ $11.49
Drink ............... $2.29
Total ............... $13.78
Paid with Visa ending in 1234.""",
      False, None, "low", "other"),

    E("order_confirmation", ["receipt"],
      "Order #44120 confirmed",
      "Gadget Depot <orders@gadgetdepot.example.com>", "2026-10-23T18:00:00-04:00", """
Thanks for shopping with Gadget Depot! Your order #44120 (USB-C hub) has been
confirmed and will ship in 1–2 business days. Estimated delivery: October 28.""",
      False, None, "low", "other", headers=UNSUB,
      notes="Mentions a future date but needs nothing."),

    E("package_delivered", ["receipt"],
      "Your package was delivered",
      "Parcel Express <tracking@parcelexpress.example.com>", "2026-10-26T15:20:00-04:00", """
Your package was delivered at 3:12 PM and left at the front door.
Tracking number: 1Z999AA10123456784""",
      False, None, "low", "other", headers=UNSUB),
]


def main():
    ids = [d["id"] for d in DATA]
    assert len(ids) == len(set(ids)), "duplicate ids"
    path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(path, "w") as f:
        json.dump(DATA, f, indent=2)
    n_act = sum(d["expected"]["is_actionable"] for d in DATA)
    print(f"Wrote {len(DATA)} emails ({n_act} actionable, {len(DATA) - n_act} not) to {path}")


if __name__ == "__main__":
    main()
