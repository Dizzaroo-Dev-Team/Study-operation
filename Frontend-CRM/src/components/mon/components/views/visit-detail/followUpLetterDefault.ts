/**
 * Default Monitoring Visit Follow-Up Letter (clinical format).
 * Bracket placeholders are merged from visit overview via FollowUpLetterTab.
 */
export const FOLLOW_UP_LETTER_DEFAULT_TEMPLATE = `Date: [Letter Date]

To:
[PI Name With Degree]
[Site Name Line]
[Department Division]
[Address Street]
[Address City Region Postal Country]

From:
[Monitor Name Full]
[Sponsor Organization Name]
[Monitor Email Address]
[Monitor Telephone Number]

Subject: Follow-Up Letter — Monitoring Visit | [Study Display Name] | Protocol [Study Protocol Ref] | Site [Clinical Site Identifier] | Visit Date: [Clinical Visit Date]

--------------------------------------------------------------------------------
1. INTRODUCTION
--------------------------------------------------------------------------------

Dear [PI Dear Name],

This letter is issued as a follow-up to the monitoring visit conducted at [Site Name Line] (Site ID: [Clinical Site Identifier]) on [Clinical Visit Date] as part of the [Study Display Name] (Protocol Number: [Study Protocol Ref]) sponsored by [Sponsor Organization Name].

The purpose of this correspondence is to formally document the findings, observations, and action items identified during the visit, and to confirm the timelines required for their resolution. We appreciate the cooperation and assistance provided by you and your study team during the visit.

--------------------------------------------------------------------------------
2. SUMMARY OF FINDINGS
--------------------------------------------------------------------------------

The following findings were identified during the monitoring visit. Each finding is categorized by area and assigned a severity level: Critical, Major, or Minor.

| Category              | Finding Description | Severity | Reference |
|-----------------------|---------------------|----------|-----------|
| Regulatory Documents  |                     |          |           |
| Informed Consent      |                     |          |           |
| Source Data / SDV     |                     |          |           |
| IP Management         |                     |          |           |
| Safety Reporting      |                     |          |           |
| Protocol Compliance   |                     |          |           |
| Data Quality          |                     |          |           |
| Staff Training        |                     |          |           |

(Optional — Provide a brief narrative summary highlighting the most important observations, positive findings, and areas requiring immediate attention.)

--------------------------------------------------------------------------------
3. ACTION ITEMS
--------------------------------------------------------------------------------

The table below summarizes all action items arising from this monitoring visit (from the Visit Findings tab). Please ensure that all items are addressed within the specified timelines and that a written response is submitted to the monitor.

| # | Action Item / Finding | Required Action | Due Date | Assign To | Priority |
|---|-----------------------|-----------------|----------|---------|

--------------------------------------------------------------------------------
4. TIMELINES FOR RESOLUTION
--------------------------------------------------------------------------------

| Severity Level | Required Response Timeline | Escalation Timeline |
|----------------|----------------------------|---------------------|
| Critical       | Within 48 hours of receipt | Immediate sponsor notification |
| Major          | Within 7 calendar days | Escalation if unresolved within 14 days |
| Minor          | Within 14 calendar days | Escalation if unresolved within 30 days |

Please confirm receipt of this letter and provide your written response addressing each action item. Your response should be directed to [Monitor Email Address] with a copy to [Sponsor Contact Name And Email].

--------------------------------------------------------------------------------
5. CLOSING REMARKS
--------------------------------------------------------------------------------

We recognize and appreciate the efforts of your team in conducting this study in accordance with Good Clinical Practice (ICH-GCP E6 R2) guidelines and applicable regulatory requirements. The findings noted in this letter are intended to support the continuous improvement of study conduct and data quality at your site.

Should you require clarification on any of the items raised in this letter, or if you wish to discuss any of the findings, please do not hesitate to contact the undersigned monitor. We look forward to your timely response and continued collaboration.

--------------------------------------------------------------------------------
AUTHORIZATION
--------------------------------------------------------------------------------

Monitor Name          [Monitor Name Full]
Monitor Signature     
Date                  [Authorization Date]
Sponsor / CRO Contact [Sponsor Contact Role Line]

CONFIDENTIAL                                                          Page 1 of 2
`;
