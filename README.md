# Welcome Terminator 👋

Hello Team **Terminator** from **Adhichunchanagiri Institute of Technology**,

Welcome to the Hackathon! We're excited to have you on board and can't wait to see what you'll build under the theme **"Digital solutions for rural education"** 

## Team Details

- **Team Number:** 74  
- **Team Name:** Terminator
- **Team Leader:** Hithashree KS  
- **Email:** hithashreeskardya@gmail.com  
- **Phone:** 9902242268  

### Team Members:
- Sanjay SR 
- Sanvi CV 
- Poorvi V 

## Problem Statement

> **Problem Statement: ElderWisdom Archive Rural communities possess valuable traditional knowledge and...**

---

### Let's Get Started 

This repository has been set up for your hackathon project. Use it to manage your code, collaborate, and share your progress.

**Important Guidelines - Please Read Carefully**

- Do **not** make any commits **before the allotted start date and time**. Early commits may result in getting caught.
- Commit your work **regularly** to showcase your progress throughout the hackathon.

- Maintain **professionalism and integrity** at all times. Any form of plagiarism or rule-breaking will lead to strict action.

Let's keep it fair, fun, and impactful! 
---

**Good luck, Team Terminator! Happy coding!**

If you need any support during the hackathon, don't hesitate to reach out to the co-ordinators.

Cheers,  
_Advaya Hackathon Team_

---

## EduPulse Application

### Setting Up Twilio Integration for IVR Calls

The EduPulse application has integrated Twilio for making Interactive Voice Response (IVR) calls to collect student feedback on teachers. Follow these steps to set up the Twilio integration:

1. **Sign up for a Twilio Account**
   - Go to [Twilio](https://www.twilio.com) and sign up for an account
   - Purchase a phone number or use a trial number provided by Twilio

2. **Get Your Twilio Credentials**
   - Copy your Twilio Account SID and Auth Token from the Twilio Dashboard
   - Note your Twilio phone number (must include the country code, e.g., +12345678900)

3. **Configure Twilio Credentials**
   - Option 1: Set environment variables in your system:
     ```
     TWILIO_ACCOUNT_SID=your_account_sid
     TWILIO_AUTH_TOKEN=your_auth_token
     TWILIO_PHONE_NUMBER=your_twilio_phone_number
     ```
   
   - Option 2 (Recommended): Directly update the values in the `edupulse_app.py` file:
     - Locate these lines in the file:
     ```python
     app.config['TWILIO_ACCOUNT_SID'] = os.environ.get('TWILIO_ACCOUNT_SID', '')
     app.config['TWILIO_AUTH_TOKEN'] = os.environ.get('TWILIO_AUTH_TOKEN', '')
     app.config['TWILIO_PHONE_NUMBER'] = os.environ.get('TWILIO_PHONE_NUMBER', '')
     ```
     - Replace them with your actual credentials:
     ```python
     app.config['TWILIO_ACCOUNT_SID'] = 'your_actual_account_sid'
     app.config['TWILIO_AUTH_TOKEN'] = 'your_actual_auth_token'
     app.config['TWILIO_PHONE_NUMBER'] = '+12345678900'  # Your Twilio number with country code
     ```

4. **Set Up Public URL for Webhooks**
   - Twilio needs a public URL to send call events to your application
   - For local development, you can use [ngrok](https://ngrok.com) to expose your local server:
     ```
     ngrok http 5000
     ```
   - Update the callback URL in `edupulse_app.py`:
     ```python
     app.config['TWILIO_CALLBACK_URL'] = 'https://your-ngrok-url.ngrok.io/ivr/callback'
     ```

5. **Test Phone Numbers**
   - For testing, add your own phone number(s) directly in the code:
     ```python
     app.config['TEST_PHONE_NUMBERS'] = '+12345678900,+19876543210'
     ```

6. **Install Required Packages**
   - Make sure to install the Twilio package:
     ```
     pip install twilio
     ```

7. **How It Works**
   - When the principal triggers IVR calls, the system will:
     1. Create a feedback request in the database
     2. Initialize calls to the specified number of students
     3. When a student answers, they'll hear instructions and be asked to rate the teacher
     4. The student presses a number (1-5) on their phone keypad
     5. The rating is recorded in the database
     6. The teacher's overall rating is updated

   - In development mode (without Twilio credentials), the system will use the simulated client.
   - In production mode (with valid Twilio credentials), real calls will be made.

8. **Using the IVR Feature**
   - Log in as a principal
   - Navigate to the Principal Dashboard
   - Click on "Trigger IVR Calls" button
   - Select teachers and specify the number of students to call
   - Click "Trigger IVR Calls" to initiate the process