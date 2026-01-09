#!/usr/bin/env python3
"""
BFMR Deal Monitor - GitHub Actions Version
Runs once per invocation (GitHub Actions handles scheduling)
"""

import requests
import json
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

class BFMRMonitor:
    def __init__(self):
        """Initialize from environment variables"""
        self.api_key = os.getenv('BFMR_API_KEY')
        self.api_secret = os.getenv('BFMR_API_SECRET')
        self.base_url = "https://api.bfmr.com"
        
        self.email_config = {
            'smtp_server': os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com'),
            'smtp_port': int(os.getenv('EMAIL_SMTP_PORT', '587')),
            'from_email': os.getenv('EMAIL_FROM'),
            'to_email': os.getenv('EMAIL_TO'),
            'password': os.getenv('EMAIL_PASSWORD')
        }
        
        # Validate configuration
        if not all([self.api_key, self.api_secret, 
                   self.email_config['from_email'], 
                   self.email_config['password']]):
            raise ValueError("Required environment variables not set")
        
        # File to store seen deals
        self.seen_deals_file = Path("seen_deals.json")
        self.seen_deals = self.load_seen_deals()
        
    def load_seen_deals(self):
        """Load previously seen deals from file"""
        if self.seen_deals_file.exists():
            try:
                with open(self.seen_deals_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_seen_deals(self):
        """Save seen deals to file"""
        with open(self.seen_deals_file, 'w') as f:
            json.dump(self.seen_deals, f, indent=2)
    
    def get_deals(self):
        """Fetch current deals from BFMR API"""
       endpoints_to_try = [
            f"{self.base_url}/api/v2/deals",
            f"{self.base_url}/api/deals",
            f"{self.base_url}/deals",
        ]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "X-API-Secret": self.api_secret,
        }
        
        for endpoint in endpoints_to_try:
            try:
                print(f"Trying endpoint: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=10)
                print(f"Status code: {response.status_code}")
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    print("Authentication failed")
                    return None
            except Exception as e:
                print(f"Error with {endpoint}: {e}")
                continue
        
        return None
    
    def format_deal_info(self, deal):
        """Format deal information for email"""
        deal_id = deal.get('id', 'Unknown')
        title = deal.get('title') or deal.get('name') or deal.get('product_name', 'No title')
        price = deal.get('price', 'N/A')
        payout = deal.get('payout') or deal.get('buyer_price', 'N/A')
        url = deal.get('url') or deal.get('product_url', '')
        store = deal.get('store') or deal.get('retailer', 'Amazon')
        quantity = deal.get('quantity', 'N/A')
        
        return f"""
Deal ID: {deal_id}
Title: {title}
Store: {store}
Price: ${price}
Your Payout: ${payout}
Quantity: {quantity}
URL: {url}
        """.strip()
    
    def send_email(self, subject, body):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.email_config['smtp_server'], 
                            self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['from_email'], 
                           self.email_config['password'])
                server.send_message(msg)
            
            print(f"✅ Email sent: {subject}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    def check_for_new_deals(self):
        """Check for new deals and send notifications"""
        print(f"\n{'='*60}")
        print(f"BFMR Deal Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}\n")
        
        deals_data = self.get_deals()
        
        if not deals_data:
            print("⚠️  Could not fetch deals")
            return
        
        # Extract deals from response
        deals = deals_data
        if isinstance(deals_data, dict):
            deals = deals_data.get('deals', deals_data.get('data', []))
        
        print(f"📊 Total deals found: {len(deals) if deals else 0}")
        
        if not deals:
            print("No deals currently available")
            return
        
        # Find new deals
        new_deals = []
        for deal in deals:
            deal_id = str(deal.get('id', deal.get('deal_id', '')))
            
            if deal_id and deal_id not in self.seen_deals:
                new_deals.append(deal)
                self.seen_deals[deal_id] = {
                    'first_seen': datetime.now().isoformat(),
                    'title': deal.get('title') or deal.get('name', 'Unknown')
                }
        
        if new_deals:
            print(f"\n🎉 Found {len(new_deals)} NEW deal(s)!")
            
            # Build email
            email_body = f"Found {len(new_deals)} new BFMR deal(s):\n\n"
            email_body += "=" * 60 + "\n\n"
            
            for deal in new_deals:
                email_body += self.format_deal_info(deal)
                email_body += "\n\n" + "=" * 60 + "\n\n"
            
            email_body += f"\nView all deals: https://www.buyformeretail.com/deals\n"
            email_body += f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            
            # Send email
            self.send_email(
                f"🚨 {len(new_deals)} New BFMR Deal(s) Available!",
                email_body
            )
            
            # Save updated seen deals
            self.save_seen_deals()
            print(f"✅ Saved {len(self.seen_deals)} total deals to tracking file")
        else:
            print("✓ No new deals (all deals already seen)")
        
        print(f"\n{'='*60}\n")


def main():
    """Main function"""
    try:
        monitor = BFMRMonitor()
        monitor.check_for_new_deals()
        return 0
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print("\nRequired GitHub Secrets:")
        print("  - BFMR_API_KEY")
        print("  - BFMR_API_SECRET")
        print("  - EMAIL_FROM")
        print("  - EMAIL_TO")  
        print("  - EMAIL_PASSWORD")
        print("  - EMAIL_SMTP_SERVER (optional, defaults to smtp.gmail.com)")
        print("  - EMAIL_SMTP_PORT (optional, defaults to 587)")
        return 1
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":

    exit(main())
