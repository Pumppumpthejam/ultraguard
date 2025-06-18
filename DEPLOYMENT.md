# Ultraguard Deployment Guide

## 🚀 Deploy to Render

### Prerequisites
- GitHub account with your Ultraguard repository
- Render account (free tier available)

### Step 1: Prepare Your Repository

1. **Push your code to GitHub:**
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

2. **Ensure these files are in your repository:**
   - `render.yaml` - Render configuration
   - `requirements.txt` - Python dependencies
   - `Procfile` - Process definition
   - `gunicorn.conf.py` - Gunicorn configuration
   - `config.py` - Application configuration
   - `run.py` - Application entry point

### Step 2: Deploy on Render

1. **Go to [render.com](https://render.com) and sign up/login**

2. **Click "New +" and select "Blueprint"**

3. **Connect your GitHub repository:**
   - Select your Ultraguard repository
   - Render will automatically detect the `render.yaml` file

4. **Review the configuration:**
   - **Web Service:** `ultraguard-app`
   - **Database:** `ultraguard-db` (PostgreSQL)
   - **Environment:** Python

5. **Click "Apply" to start deployment**

### Step 3: Configure Environment Variables

After deployment, go to your web service dashboard and add these environment variables:

```
FLASK_ENV=production
FLASK_CONFIG=production
ADMIN_USERNAME=your-admin-email@example.com
ADMIN_PASSWORD=your-secure-password
```

### Step 4: Initialize the Database

1. **Go to your web service dashboard on Render**

2. **Open the Shell/Console**

3. **Run the deployment script:**
   ```bash
   python deploy.py
   ```

4. **Verify the output shows:**
   - Database migrations completed
   - Admin user created
   - Sample client created

### Step 5: Access Your Application

1. **Your app will be available at:** `https://your-app-name.onrender.com`

2. **Admin Portal:** `https://your-app-name.onrender.com/admin/login`
   - Username: `your-admin-email@example.com`
   - Password: `your-secure-password`

3. **Client Portal:** `https://your-app-name.onrender.com/client_portal/login`

### Step 6: Set Up Custom Domain (Optional)

1. **In your Render dashboard, go to Settings**

2. **Click "Custom Domains"**

3. **Add your domain (e.g., `app.yourdomain.com`)**

4. **Update your DNS records as instructed by Render**

## 🔧 Troubleshooting

### Common Issues:

1. **Build fails:**
   - Check `requirements.txt` has all dependencies
   - Verify Python version compatibility

2. **Database connection fails:**
   - Ensure `DATABASE_URL` is set correctly
   - Check PostgreSQL service is running

3. **App crashes on startup:**
   - Check logs in Render dashboard
   - Verify `SECRET_KEY` is set
   - Ensure all environment variables are configured

### Viewing Logs:

1. **In Render dashboard, go to your web service**
2. **Click "Logs" tab**
3. **Check for error messages**

## 🔒 Security Checklist

- [ ] Change default admin password
- [ ] Set strong `SECRET_KEY`
- [ ] Configure HTTPS (automatic on Render)
- [ ] Review and update environment variables
- [ ] Test all user roles and permissions

## 📊 Monitoring

- **Render provides built-in monitoring**
- **Check "Metrics" tab for performance data**
- **Set up alerts for downtime**

## 🔄 Updates

To update your application:

1. **Push changes to GitHub**
2. **Render automatically redeploys**
3. **Run `python deploy.py` if database changes are needed**

## 📞 Support

- **Render Documentation:** [docs.render.com](https://docs.render.com)
- **Ultraguard Issues:** Check your repository issues
- **Community:** Stack Overflow, Reddit r/flask

---

**Your Ultraguard application is now live! 🎉** 